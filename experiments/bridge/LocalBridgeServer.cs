// Local transport only. The caller supplies the handler; no gameplay API exists here.
using System;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Reflection;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

public sealed class LocalBridgeServer : IDisposable {
    [DllImport("libc",SetLastError=true)] static extern int chmod(string path,uint mode);
    readonly Socket listener;
    readonly Thread worker;
    readonly Func<JObject,JObject> handler;
    readonly Queue<Ticket> pending=new Queue<Ticket>();
    readonly HashSet<string> ids=new HashSet<string>();
    readonly Queue<string> idOrder=new Queue<string>();
    volatile bool stopped;
    public readonly string Path;
    public readonly string Session;
    sealed class Ticket {
        public string Raw,Reply;
        public volatile bool Cancelled;
        public DateTime Deadline;
        public readonly ManualResetEvent Done=new ManualResetEvent(false);
    }
    sealed class UnixEndpoint:EndPoint {
        readonly string name;
        public UnixEndpoint(string path){name=path;}
        public override AddressFamily AddressFamily {get{return AddressFamily.Unix;}}
        public override SocketAddress Serialize() {
            byte[] b=Encoding.UTF8.GetBytes(name);
            if(b.Length>100)throw new ArgumentException("Socket path too long");
            var address=new SocketAddress(AddressFamily.Unix,b.Length+3);
            MethodInfo setter=typeof(SocketAddress).GetProperty("Item").GetSetMethod();
            if(setter!=null)for(int i=0;i<b.Length;i++)setter.Invoke(address,new object[]{i+2,b[i]});
            else {
                // Current stripped game System.dll omits the setter; its verified backing field remains.
                FieldInfo field=typeof(SocketAddress).GetField("m_Buffer",BindingFlags.Instance|BindingFlags.NonPublic);
                if(field==null)throw new NotSupportedException("Unsupported SocketAddress layout");
                byte[] raw=field.GetValue(address) as byte[];
                if(raw==null||raw.Length<b.Length+3)throw new NotSupportedException("Invalid SocketAddress buffer");
                Buffer.BlockCopy(b,0,raw,2,b.Length);
                FieldInfo changed=typeof(SocketAddress).GetField("m_changed",BindingFlags.Instance|BindingFlags.NonPublic);
                if(changed!=null)changed.SetValue(address,true);
            }
            return address;
        }
        public override EndPoint Create(SocketAddress address){return this;}
    }
    public LocalBridgeServer(string path,string session,Func<JObject,JObject> handle) {
        Path=path;Session=session;handler=handle;
        if(File.Exists(path))throw new IOException("Existing socket must be inspected first");
        listener=new Socket(AddressFamily.Unix,SocketType.Stream,ProtocolType.Unspecified);
        try {
            listener.Bind(new UnixEndpoint(path));
            if(chmod(path,384)!=0)throw new IOException("Socket permissions failed");
            listener.Listen(2);listener.Blocking=false;
        }catch{listener.Close();throw;}
        worker=new Thread(Work);worker.IsBackground=true;worker.Start();
    }
    static string Reply(string id,string status,string reason) {
        var response=new JObject();response["id"]=id;response["status"]=status;response["reason"]=reason;return response.ToString(Formatting.None);
    }
    void Work() {
        while(!stopped) {
            Socket connection=null;Ticket ticket=null;
            try {
                connection=listener.Accept();connection.Blocking=true;connection.SetSocketOption(SocketOptionLevel.Socket,SocketOptionName.ReceiveTimeout,1000);connection.SetSocketOption(SocketOptionLevel.Socket,SocketOptionName.SendTimeout,1000);
                byte[] buffer=new byte[4097];int count=0;DateTime deadline=DateTime.UtcNow.AddSeconds(2);
                while(count<buffer.Length&&DateTime.UtcNow<deadline) {
                    int n=connection.Receive(buffer,count,buffer.Length-count,SocketFlags.None);
                    if(n==0)break;count+=n;
                    if(Array.IndexOf(buffer,(byte)10,0,count)>=0)break;
                }
                int end=Array.IndexOf(buffer,(byte)10,0,count);
                if(end<0||end>4096)continue;
                ticket=new Ticket{Raw=Encoding.UTF8.GetString(buffer,0,end),Deadline=deadline};
                lock(pending){if(pending.Count>=4)continue;pending.Enqueue(ticket);}
                if(!ticket.Done.WaitOne(2500)){ticket.Cancelled=true;continue;}
                byte[] reply=Encoding.UTF8.GetBytes(ticket.Reply+"\n");int sent=0;
                while(sent<reply.Length){int n=connection.Send(reply,sent,reply.Length-sent,SocketFlags.None);if(n==0)break;sent+=n;}
            }catch(SocketException){if(!stopped)Thread.Sleep(50);}catch(ObjectDisposedException){}catch(IOException){}
            finally{if(ticket!=null)ticket.Cancelled=true;if(connection!=null)connection.Close();}
        }
    }
    // Must be called on the game main thread. At most one request per Update.
    public void Pump() {
        Ticket t;
        lock(pending){if(pending.Count==0)return;t=pending.Dequeue();}
        if(t.Cancelled||stopped||DateTime.UtcNow>t.Deadline){t.Reply=Reply("","rejected","expired");t.Done.Set();return;}
        string id="";
        try {
            // Only a flat JSON object of strings/integers is allowed. Reject duplicate keys.
            var names=new HashSet<string>();
            using(var reader=new JsonTextReader(new StringReader(t.Raw))) {
                while(reader.Read()) {
                    if(reader.TokenType==JsonToken.StartObject||reader.TokenType==JsonToken.EndObject) { if(reader.Depth!=0)throw new ArgumentException(); }
                    else if(reader.TokenType==JsonToken.PropertyName) { if(reader.Depth!=1||!names.Add((string)reader.Value)||names.Count>12)throw new ArgumentException(); }
                    else if(reader.Depth!=1||(reader.TokenType!=JsonToken.String&&reader.TokenType!=JsonToken.Integer))throw new ArgumentException();
                }
            }
            JObject request=JObject.Parse(t.Raw);
            if(request==null)throw new ArgumentException();
            JToken token=request["id"];
            if(token==null||token.Type!=JTokenType.String)throw new ArgumentException();
            id=(string)token;
            if(id.Length!=32)throw new ArgumentException();
            foreach(char c in id)if(!((c>='0'&&c<='9')||(c>='a'&&c<='f')))throw new ArgumentException();
            if(request["version"]==null||request["version"].Type!=JTokenType.Integer||(int)request["version"]!=1||request["session"]==null||request["session"].Type!=JTokenType.String||(string)request["session"]!=Session)throw new ArgumentException();
            if(request["expiresMs"]==null||request["expiresMs"].Type!=JTokenType.Integer)throw new ArgumentException();
            long now=(long)(DateTime.UtcNow-new DateTime(1970,1,1,0,0,0,DateTimeKind.Utc)).TotalMilliseconds;
            long expiry=(long)request["expiresMs"];
            if(expiry<now||expiry>now+5000){t.Reply=Reply(id,"rejected","expired");}
            else if(!ids.Add(id)){t.Reply=Reply(id,"rejected","duplicate");}
            else {
                idOrder.Enqueue(id);if(idOrder.Count>2048)ids.Remove(idOrder.Dequeue());
                // Unknown actions, stale game/turn/options, and results must be checked by the handler.
                try { JObject response=handler(request);response["id"]=id;t.Reply=response.ToString(Formatting.None); }
                catch(Exception) { t.Reply=Reply(id,"unknown","handler_failed_after_dispatch"); }
            }
        }catch(Exception){t.Reply=Reply(id,"rejected","invalid_request_or_handler_error");}
        finally{t.Done.Set();}
    }
    public void Dispose() {
        stopped=true;
        lock(pending){foreach(Ticket t in pending){t.Cancelled=true;t.Done.Set();}pending.Clear();}
        if(Thread.CurrentThread!=worker)worker.Join(4000);
        listener.Close();
        try{File.Delete(Path);}catch(IOException){}
    }
}
