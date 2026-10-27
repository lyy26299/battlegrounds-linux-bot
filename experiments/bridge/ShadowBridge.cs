using System;
using System.IO;
using System.Text;
using System.Collections;
using System.Collections.Generic;
using System.Reflection;
using System.Linq.Expressions;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Globalization;
using BepInEx;
using BepInEx.Unity.Mono;
using UnityEngine;
using UnityEngine.Rendering;

[BepInPlugin("local.battlegrounds.shadow", "Battlegrounds Shadow Bridge", "0.1.0")]
public sealed class ShadowBridge : BaseUnityPlugin {
    string root;
    float next;
    long updates;
    int desiredRenderInterval=1;
    float inputGraceUntil;
    int originalRenderInterval=1;
    FieldInfo renderIntervalField;
    void SetRenderInterval(int interval) {
        if(interval!=1 && interval!=2)throw new InvalidOperationException("Unsupported render interval");
        if(OnDemandRendering.renderFrameInterval==interval)return;
        if(renderIntervalField==null) {
            renderIntervalField=typeof(OnDemandRendering).GetField("m_RenderFrameInterval",BindingFlags.Static|BindingFlags.NonPublic);
            if(renderIntervalField==null || renderIntervalField.FieldType!=typeof(int) || renderIntervalField.IsInitOnly)throw new InvalidOperationException("Render control unavailable");
        }
        renderIntervalField.SetValue(null,interval);
    }
    string buildFailure;
    readonly string session=Guid.NewGuid().ToString("N");
    readonly int processId=System.Diagnostics.Process.GetCurrentProcess().Id;
    object previousGameEntity;
    string previousGameUuid;
    string gameId="";
    Type gameType,timerType;
    int combatTag=-1;
    Func<object,int,int> getTag;
    Func<object,int> availableResources;
    [DllImport("libc",SetLastError=true)] static extern int chmod(string path,uint mode);
    [DllImport("libc",SetLastError=true)] static extern int rename(string from,string to);
    readonly Dictionary<string,FieldInfo> fields = new Dictionary<string,FieldInfo>();
    void Awake() {
        root=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),".local/state/battlegrounds-bot/bridge");
        Directory.CreateDirectory(root);
        if(chmod(root,448)!=0)throw new IOException("Cannot protect bridge directory");
        originalRenderInterval=OnDemandRendering.renderFrameInterval;
        Logger.LogInfo("State reader loaded; gameplay actions disabled; combat rendering is opt-in.");
    }
    object Field(object obj,string name) {
        if(obj==null)throw new InvalidOperationException("Missing object");
        Type t=obj.GetType();string key=t.FullName+":"+name;FieldInfo f;
        if(!fields.TryGetValue(key,out f)) {
            for(Type c=t;c!=null;c=c.BaseType) {
                f=c.GetField(name,BindingFlags.Instance|BindingFlags.NonPublic|BindingFlags.Public|BindingFlags.DeclaredOnly);
                if(f!=null)break;
            }
            if(f==null)throw new MissingFieldException(t.FullName,name);
            fields[key]=f;
        }
        return f.GetValue(obj);
    }
    IEnumerable<object> Values(object map) {
        int n=0;
        foreach(object pair in (IEnumerable)map) {
            if(++n>8192)throw new InvalidOperationException("Collection limit");
            PropertyInfo p=pair.GetType().GetProperty("Value");
            if(p==null)throw new InvalidOperationException("Unsupported map entry");
            object value=p.GetValue(pair,null);if(value!=null)yield return value;
        }
    }
    int Tag(object entity,int key) {
        if(getTag==null) {
            foreach(MethodInfo m in entity.GetType().GetMethods(BindingFlags.Instance|BindingFlags.Public|BindingFlags.NonPublic)) {
                ParameterInfo[] ps=m.GetParameters();
                if(m.Name!="GetTag"||ps.Length!=1||ps[0].ParameterType.Name!="GAME_TAG"||m.ReturnType!=typeof(int))continue;
                var e=Expression.Parameter(typeof(object),"entity");var k=Expression.Parameter(typeof(int),"tag");
                getTag=Expression.Lambda<Func<object,int,int>>(Expression.Call(Expression.Convert(e,m.DeclaringType),m,Expression.Convert(k,ps[0].ParameterType)),e,k).Compile();break;
            }
            if(getTag==null)throw new MissingMethodException("Validated GetTag method missing");
        }
        return getTag(entity,key);
    }
    int AvailableResources(object player) {
        if(availableResources==null) {
            MethodInfo m=player.GetType().GetMethod("GetNumAvailableResources",BindingFlags.Public|BindingFlags.NonPublic|BindingFlags.Instance,null,Type.EmptyTypes,null);
            if(m==null||m.ReturnType!=typeof(int))throw new MissingMethodException("Resource getter missing");
            var e=Expression.Parameter(typeof(object),"player");
            availableResources=Expression.Lambda<Func<object,int>>(Expression.Call(Expression.Convert(e,m.DeclaringType),m),e).Compile();
        }
        return availableResources(player);
    }
    object Property(object obj,string name) { return obj.GetType().GetProperty(name).GetValue(obj,null); }
    int Count(object value) { return value==null?0:Convert.ToInt32(Property(value,"Count")); }
    readonly Dictionary<string,MethodInfo> methods=new Dictionary<string,MethodInfo>();
    object Call(object obj,string name) {
        string key=obj.GetType().FullName+":"+name;MethodInfo method;
        if(!methods.TryGetValue(key,out method)) {
            method=obj.GetType().GetMethod(name,BindingFlags.Public|BindingFlags.NonPublic|BindingFlags.Instance,null,Type.EmptyTypes,null);
            if(method==null)throw new MissingMethodException(name);methods[key]=method;
        }
        return method.Invoke(obj,null);
    }
    string Position(object entity) {
        try {
            object card=Call(entity,"GetCard");if(card==null)return ",\"input_ready\":false";
            bool ready=(bool)Call(card,"IsInputEnabled");
            Component actor=Call(card,"GetActor") as Component;
            Camera camera=Camera.main;
            if(actor==null||camera==null||Screen.width<=0||Screen.height<=0)return ",\"input_ready\":false";
            Vector3 pos=camera.WorldToScreenPoint(actor.transform.position);
            double x=pos.x/Screen.width,y=1-pos.y/Screen.height;
            if(pos.z<=0||x<0||x>1||y<0||y>1)return ",\"input_ready\":false";
            return ",\"input_ready\":"+(ready?"true":"false")+",\"x\":"+x.ToString("F5",CultureInfo.InvariantCulture)+",\"y\":"+y.ToString("F5",CultureInfo.InvariantCulture);
        }catch(Exception){return ",\"input_ready\":false";}
    }
    string Snapshot() {
        if(buildFailure!=null)return "\"available\":false,\"reason\":\"unsupported_build\"";
        if(gameType==null) {
            foreach(Assembly a in AppDomain.CurrentDomain.GetAssemblies())if(a.GetName().Name=="Assembly-CSharp") {
                using(var hash=SHA256.Create())using(var input=File.OpenRead(a.Location)) {
                    string actual=BitConverter.ToString(hash.ComputeHash(input)).Replace("-","").ToLowerInvariant();
                    if(actual!="7f81d2ab2277958dea4351c41812921a00ee263a6a7abf1a5cfb4eb0794f26e5"){buildFailure="hash_mismatch";throw new InvalidOperationException("Unsupported game build");}
                }
                combatTag=Convert.ToInt32(Enum.Parse(a.GetType("GAME_TAG"),"BACON_IN_COMBAT_PHASE"));
                gameType=a.GetType("GameState");timerType=a.GetType("TurnTimer");
            }
        }
        if(gameType==null)return "\"available\":false,\"reason\":\"assembly_not_ready\"";
        object game=gameType.GetField("s_instance",BindingFlags.Static|BindingFlags.NonPublic|BindingFlags.Public).GetValue(null);
        if(game==null)return "\"available\":false,\"reason\":\"no_game\"";
        object player=null;
        foreach(object p in Values(Field(game,"m_playerMap")))if((bool)Field(p,"m_local")) {
            if(player!=null)throw new InvalidOperationException("Ambiguous local player");player=p;
        }
        if(player==null)return "\"available\":false,\"reason\":\"no_local_player\"";
        int controller=Tag(player,30);
        if(controller<0)throw new InvalidOperationException("Missing player identity");
        var cards=new List<string>();
        foreach(object entity in Values(Field(game,"m_entityMap"))) {
            if(Tag(entity,50)!=controller)continue;
            int zone=Tag(entity,49),type=Tag(entity,202),pos=Tag(entity,263);
            if((zone!=1&&zone!=3)||(type!=4&&type!=5)||pos<=0)continue;
            cards.Add("{\"entity\":"+Tag(entity,53)+",\"zone\":"+zone+",\"position\":"+pos+",\"card_type\":"+type+Position(entity)+"}");
        }
        int gold=AvailableResources(player);
        object gameEntity=Field(game,"m_gameEntity");
        string gameUuid=gameEntity==null?null:Property(gameEntity,"Uuid") as string;
        if(!System.Object.ReferenceEquals(gameEntity,previousGameEntity)||gameUuid!=previousGameUuid) {
            previousGameEntity=gameEntity;previousGameUuid=gameUuid;gameId=Guid.NewGuid().ToString("N");
        }
        int combat=gameEntity==null?-1:Tag(gameEntity,combatTag);
        int turn=gameEntity==null?-1:Tag(gameEntity,20);
        if(combat==1 && !(bool)Field(game,"m_gameOver") && File.Exists(Path.Combine(root,"low-render.enabled")))desiredRenderInterval=2;
        object options=Field(game,"m_options");
        string seconds="null";int timerState=-1;
        object timer=timerType.GetField("s_instance",BindingFlags.Static|BindingFlags.NonPublic|BindingFlags.Public).GetValue(null);
        if(timer!=null) {
            timerState=Convert.ToInt32(Field(timer,"m_state"));
            if((bool)Field(timer,"m_currentTimerBelongsToFriendlySidePlayer")&&!(bool)Field(timer,"m_waitingForTurnStartManagerFinish")) {
                float remaining=(float)Call(timer,"ComputeCountdownRemainingSec");
                if(!float.IsNaN(remaining)&&!float.IsInfinity(remaining)&&remaining>=0&&remaining<=300)seconds=remaining.ToString("F2",CultureInfo.InvariantCulture);
            }
        }
        int optionsId=options==null?-1:Convert.ToInt32(Property(options,"ID"));
        var legal=new List<string>();var eligible=new HashSet<int>();int optionIndex=0;
        if(options!=null)foreach(object option in (IEnumerable)Property(options,"List")) {
            if(optionIndex>=256)throw new InvalidOperationException("Options limit");
            object main=Property(option,"Main");
            if(main!=null) {
                int id=Convert.ToInt32(Property(main,"ID"));
                object error=Property(main,"PlayErrorInfo");
                int playError=error==null?0:Convert.ToInt32(Property(error,"PlayError"));
                eligible.Add(id);
                legal.Add("{\"index\":"+optionIndex+",\"entity\":"+id+",\"type\":"+Convert.ToInt32(Property(option,"Type"))+",\"error\":"+playError+",\"targets\":"+Count(Property(main,"Targets"))+",\"subs\":"+Count(Property(option,"Subs"))+",\"keyword\":"+Convert.ToInt32(Property(main,"PowerKeyword"))+"}");
            }
            optionIndex++;
        }
        object last=Field(game,"m_lastSelectedOption"),lastPacket=Field(game,"m_lastOptions");
        string selected="null";
        if(last!=null&&lastPacket!=null)selected="{\"options_id\":"+Convert.ToInt32(Property(lastPacket,"ID"))+",\"main\":"+Field(last,"m_main")+",\"sub\":"+Field(last,"m_sub")+",\"target\":"+Field(last,"m_target")+",\"position\":"+Field(last,"m_position")+"}";
        var shop=new List<string>();
        if(combat==0 && !(bool)Field(game,"m_busy") && !(bool)Field(game,"m_gameOver"))
        foreach(object entity in Values(Field(game,"m_entityMap"))) {
            int id=Tag(entity,53),pos=Tag(entity,263);
            if(eligible.Contains(id)&&Tag(entity,50)!=controller&&Tag(entity,49)==1&&Tag(entity,202)==4&&pos>0)
                shop.Add("{\"entity\":"+id+",\"position\":"+pos+Position(entity)+"}");
        }
        return "\"available\":true,\"game_id\":\""+gameId+"\",\"game_over\":"+((bool)Field(game,"m_gameOver")?"true":"false")+",\"turn\":"+turn+",\"combat_tag\":"+combat+",\"seconds_candidate\":"+seconds+",\"timer_state\":"+timerState+",\"options_id\":"+optionsId+",\"gold_candidate\":"+gold+",\"busy\":"+((bool)Field(game,"m_busy")?"true":"false")+",\"entities\":["+String.Join(",",cards.ToArray())+"],\"shop_candidates\":["+String.Join(",",shop.ToArray())+"],\"options\":["+String.Join(",",legal.ToArray())+"],\"last_selection\":"+selected;
    }
    void OnDestroy() { try { SetRenderInterval(originalRenderInterval); } catch(Exception) {} }
    void Update() {
        updates++;
        if(Input.anyKey || Input.GetMouseButton(0) || Input.GetMouseButton(1)) {
            inputGraceUntil=Time.realtimeSinceStartup+2;
            try { SetRenderInterval(1); } catch(Exception) {}
        }
        if(Time.realtimeSinceStartup<next)return;next=Time.realtimeSinceStartup+0.5f;
        string state;desiredRenderInterval=1;
        try {state=Snapshot();}catch(Exception e){desiredRenderInterval=1;state="\"available\":false,\"reason\":\""+e.GetType().Name+"\"";}
        if(Time.realtimeSinceStartup<inputGraceUntil)desiredRenderInterval=1;
        try { SetRenderInterval(desiredRenderInterval); }
        catch(Exception) { try { SetRenderInterval(1); } catch(Exception) {} }
        string text="{\"utc\":\""+DateTime.UtcNow.ToString("O",CultureInfo.InvariantCulture)+"\",\"updates\":"+updates+",\"pid\":"+processId+",\"session\":\""+session+"\",\"rendered_frames\":"+Time.renderedFrameCount+",\"target_fps\":"+Application.targetFrameRate+",\"vsync\":"+QualitySettings.vSyncCount+",\"width\":"+Screen.width+",\"height\":"+Screen.height+",\"render_interval\":"+OnDemandRendering.renderFrameInterval+",\"control_allowed\":false,"+state+"}";
        try {
            string temp=Path.Combine(root,"shadow.tmp"),dest=Path.Combine(root,"shadow.json");
            File.WriteAllText(temp,text);if(chmod(temp,384)!=0)throw new IOException("Snapshot protection failed");if(rename(temp,dest)!=0)throw new IOException("Snapshot publish failed");
            string history=Path.Combine(root,"shadow-history.jsonl");
            if(!File.Exists(history)||new FileInfo(history).Length<33554432) {
                File.AppendAllText(history,text+"\n");chmod(history,384);
            }
        }catch(IOException){}
    }

}
