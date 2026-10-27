using System;
using System.IO;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using Newtonsoft.Json.Linq;
class TransportTest {
 static void Main() {
  string folder=System.IO.Path.Combine(System.IO.Path.GetTempPath(),"bg-ipc-"+Guid.NewGuid().ToString("N").Substring(0,6));Directory.CreateDirectory(folder);
  string path=System.IO.Path.Combine(folder,"test.sock"),session=new string('b',32),id=new string('a',32);int calls=0;
  using(var server=new LocalBridgeServer(path,session,q=>{calls++;if((string)q["action"]=="fail")throw new Exception("failure");return JObject.Parse("{\"status\":\"observed\"}");})) {
   Func<string,string> send=raw=> {
    string result=null;Exception failure=null;
    var client=new Thread(()=>{try{using(var c=new Socket(AddressFamily.Unix,SocketType.Stream,ProtocolType.Unspecified)){c.Connect(new UnixDomainSocketEndPoint(path));c.Send(Encoding.UTF8.GetBytes(raw+"\n"));var b=new byte[4096];result=Encoding.UTF8.GetString(b,0,c.Receive(b));}}catch(Exception e){failure=e;}});client.Start();
    for(int i=0;i<100&&client.IsAlive;i++){server.Pump();Thread.Sleep(10);}client.Join(3000);if(failure!=null)throw failure;if(result==null)throw new Exception("No reply");return (string)JObject.Parse(result)["status"];
   };
   Func<string,long,string> message=(identity,expiry)=>"{\"id\":\""+identity+"\",\"version\":1,\"session\":\""+session+"\",\"expiresMs\":"+expiry+",\"action\":\"status\"}";
   long now=DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
   if(send(message(id,now+3000))!="observed"||calls!=1)throw new Exception("Valid request failed");
   if(send(message(id,DateTimeOffset.UtcNow.ToUnixTimeMilliseconds()+3000))!="rejected"||calls!=1)throw new Exception("Duplicate dispatch");
   if(send(message(new string('c',32),now-1000))!="rejected"||calls!=1)throw new Exception("Expired dispatch");
   if(send(message(new string('d',32),now+60000))!="rejected"||calls!=1)throw new Exception("Unbounded expiry");
   string next=message(new string('e',32),DateTimeOffset.UtcNow.ToUnixTimeMilliseconds()+3000);
   if(send(next.Replace("\"action\":\"status\"","\"action\":\"fail\""))!="unknown"||calls!=2)throw new Exception("Handler failure mislabeled");
   if(send(next.Replace(session,new string('f',32)))!="rejected"||calls!=2)throw new Exception("Wrong session accepted");
   if(send(next.Replace("\"version\":1","\"version\":1,\"version\":1"))!="rejected"||calls!=2)throw new Exception("Duplicate field accepted");
   Console.WriteLine("7 IPC checks passed; shutdown also completes without hanging");
  }
  Directory.Delete(folder);
 }
}
