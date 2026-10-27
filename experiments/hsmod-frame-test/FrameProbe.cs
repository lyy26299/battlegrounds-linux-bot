using System;
using System.IO;
using System.Reflection;
using System.Globalization;
using System.Security.Cryptography;
using System.Runtime.InteropServices;
using BepInEx;
using BepInEx.Unity.Mono;
using UnityEngine;
[BepInPlugin("local.battlegrounds.framerateprobe","Frame Rate Probe","0.1.0")]
public sealed class FrameProbe:BaseUnityPlugin {
 string root;float next;long updates;object manager;MethodInfo setter;int original=20,applied=-1;bool captured;string error="";
 [DllImport("libc")]static extern int chmod(string p,uint m);
 [DllImport("libc")]static extern int rename(string a,string b);
 void Awake(){root=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),".local/state/battlegrounds-bot/bridge");Directory.CreateDirectory(root);chmod(root,448);}
 bool Bind(){
  if(manager!=null)return true;
  Assembly game=null,services=null;
  foreach(Assembly a in AppDomain.CurrentDomain.GetAssemblies()){if(a.GetName().Name=="Assembly-CSharp")game=a;if(a.GetName().Name=="Blizzard.T5.ServiceLocator")services=a;}
  if(game==null||services==null)return false;
  using(var h=SHA256.Create())using(var f=File.OpenRead(game.Location)){if(BitConverter.ToString(h.ComputeHash(f)).Replace("-","").ToLowerInvariant()!="7f81d2ab2277958dea4351c41812921a00ee263a6a7abf1a5cfb4eb0794f26e5")throw new InvalidOperationException();}
  Type iface=null;foreach(Assembly a in AppDomain.CurrentDomain.GetAssemblies())if(a.GetName().Name=="Blizzard.T5.GraphicsManagerInterface")iface=a.GetType("IGraphicsManager");
  if(iface==null)return false;
  foreach(var m in services.GetType("Blizzard.T5.Services.ServiceManager").GetMethods(BindingFlags.Static|BindingFlags.Public))if(m.Name=="Get"&&m.IsGenericMethodDefinition&&m.GetParameters().Length==0){manager=m.MakeGenericMethod(iface).Invoke(null,null);break;}
  if(manager==null)return false;
  setter=iface.GetMethod("UpdateTargetFramerate",new Type[]{typeof(int),typeof(bool)});
  if(setter==null)throw new MissingMethodException();
  return true;
 }
 void Apply(int fps){setter.Invoke(manager,new object[]{fps,false});applied=fps;}
 void Update(){
  updates++;if(Time.realtimeSinceStartup<next)return;next=Time.realtimeSinceStartup+1;
  try {
   if(Bind()){
    int want=-1;string path=Path.Combine(root,"frame-test-command.txt");
    if(File.Exists(path)){
     var lines=File.ReadAllLines(path);int fps;DateTime end;
     if(lines.Length==2&&Int32.TryParse(lines[0],out fps)&&(fps==5||fps==10||fps==20)&&DateTime.TryParse(lines[1],CultureInfo.InvariantCulture,DateTimeStyles.RoundtripKind,out end)&&end.ToUniversalTime()>DateTime.UtcNow&&end.ToUniversalTime()<DateTime.UtcNow.AddMinutes(3))want=fps;
    }
    if(want>0&&!captured&&Application.targetFrameRate>0){original=Application.targetFrameRate;captured=true;}
    if(captured){int target=want>0?want:original;if(applied!=target||Application.targetFrameRate!=target)Apply(target);}
   }
   error="";
  }catch(Exception e){error=e.GetType().Name;}
  string text="{\"utc\":\""+DateTime.UtcNow.ToString("O")+"\",\"pid\":"+System.Diagnostics.Process.GetCurrentProcess().Id+",\"bound\":"+(manager!=null?"true":"false")+",\"updates\":"+updates+",\"frames\":"+Time.renderedFrameCount+",\"target_fps\":"+Application.targetFrameRate+",\"original_fps\":"+original+",\"applied\":"+applied+",\"vsync\":"+QualitySettings.vSyncCount+",\"error\":\""+error+"\"}";
  var tmp=Path.Combine(root,"frame-test.tmp");File.WriteAllText(tmp,text);chmod(tmp,384);rename(tmp,Path.Combine(root,"frame-test.json"));
 }
 void OnDestroy(){if(captured&&manager!=null)try{Apply(original);}catch(Exception){}}
}
