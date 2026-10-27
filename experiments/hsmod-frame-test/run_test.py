"""One-shot HsMod-style frame-cap comparison at a confirmed match boundary."""
import os,json,time,subprocess,hashlib,signal,sys
from pathlib import Path
from datetime import datetime,timezone,timedelta
os.umask(0o077)
home=Path.home();root=home/'BattlegroundsLinux';state=home/'.local/state/battlegrounds-bot';out=state/'experiments/hsmod-frame-test';out.mkdir(parents=True,exist_ok=True)
bridge=state/'bridge';pause=state/'PAUSE';cmd=bridge/'frame-test-command.txt';drop=Path('/run/user/1000/systemd/user/bg-game.service.d/95-frame-test.conf')
plugin=home/'.local/share/hearthstone-linux-gui/game/Bin/BepInEx/plugins/BattlegroundsShadow/ShadowBridge.dll';manifest=plugin.parents[2]/'shadow-install-manifest.json'
owned=False;stopped=False;changed=False;results=[]
def ctl(*args):subprocess.run(['systemctl','--user',*args],check=True,timeout=50)
def report(stage,**kw):
 d=dict(stage=stage,at=datetime.now(timezone.utc).isoformat(),**kw);(out/'status.json').write_text(json.dumps(d));print(json.dumps(d),flush=True)
def terminate(*a):raise RuntimeError('Experiment interrupted')
signal.signal(signal.SIGTERM,terminate)
def probe():
 d=json.loads((state/'probe/state.json').read_text())
 if not 0<=time.monotonic()-d['monotonic']<4:raise RuntimeError('Stale game probe')
 return d

def heartbeat():
 d=json.loads((bridge/'frame-test.json').read_text());age=time.time()-datetime.fromisoformat(d['utc'].replace('Z','+00:00')).timestamp()
 if not 0<=age<4 or not Path('/proc/'+str(d['pid'])).exists() or d['error']:raise RuntimeError('Frame component unavailable')
 return d

def sample():
 d=heartbeat();p=probe()
 if p['pid']!=d['pid'] or p['state'].get('m_mode')!=15:raise RuntimeError('Left lobby during comparison')
 props=subprocess.check_output(['systemctl','--user','show','bg-game.service','-p','ControlGroup','-p','InvocationID'],text=True);u=dict(x.split('=',1) for x in props.splitlines());cg=Path('/sys/fs/cgroup')/u['ControlGroup'].lstrip('/')
 cpu=dict(l.split() for l in (cg/'cpu.stat').read_text().splitlines())
 return dict(t=time.monotonic(),cpu_us=int(cpu['usage_usec']),memory=int((cg/'memory.current').read_text()),swap=int((cg/'memory.swap.current').read_text()),invocation=u['InvocationID'],**d)

try:
 if pause.exists() or drop.exists():raise RuntimeError('Another maintenance operation is present')
 report('waiting_for_match_end')
 deadline=time.monotonic()+1500
 while time.monotonic()<deadline:
  try:p=probe();s=p['state']
  except (OSError,ValueError,RuntimeError):time.sleep(1);continue
  safe_resume='--resume-test' in sys.argv and s.get('game_present') is False and s.get('m_mode')==2 and subprocess.run(['systemctl','--user','is-active','--quiet','bg-bot.service']).returncode!=0
  if safe_resume or s.get('m_gameOver') is True or (s.get('m_mode')==15 and s.get('m_sceneLoaded') and not s.get('m_transitioning')):
   pause.touch(exist_ok=False);owned=True;time.sleep(1)
   s=probe()['state']
   if safe_resume or s.get('m_gameOver') is True or (s.get('m_mode')==15 and s.get('m_sceneLoaded') and not s.get('m_transitioning')):break
   pause.unlink();owned=False
  time.sleep(1)
 else:raise RuntimeError('No safe match boundary before timeout')
 report('loading_frame_probe')
 ctl('stop','bg-bot.service');stopped=True;ctl('stop','bg-game.service')
 (out/'original-plugin.bin').write_bytes(plugin.read_bytes());(out/'original-manifest.json').write_bytes(manifest.read_bytes());changed=True
 plugin.write_bytes((root/'experiments/FrameProbe.dll').read_bytes());m=json.loads(manifest.read_text());m['files']['BepInEx/plugins/BattlegroundsShadow/ShadowBridge.dll']=hashlib.sha256(plugin.read_bytes()).hexdigest();manifest.write_text(json.dumps(m))
 drop.parent.mkdir(parents=True,exist_ok=True);drop.write_text('[Service]\nExecStart=\nExecStart=/home/ubuntu/BattlegroundsLinux/.venv/bin/python /home/ubuntu/BattlegroundsLinux/state_host_shadow.py\n');ctl('daemon-reload');pause.unlink(missing_ok=True);owned=False
 (bridge/'frame-test.json').unlink(missing_ok=True);ctl('start','bg-game.service')
 for i in range(90):
  try:
   h=heartbeat()
   if h['bound'] and h['updates']>5:break
  except (OSError,ValueError,RuntimeError):pass
  time.sleep(1)
 else:raise RuntimeError('No bound graphics interface after startup')
 env=dict(os.environ,DISPLAY=':91',XAUTHORITY=str(state/'Xauthority'))
 with (out/'lobby-entry.log').open('w') as log:
  c=subprocess.run([str(root/'.venv/bin/python'),str(root/'runner.py'),'--run','--recovery-check','--state-host','--max-games','0','--max-minutes','4','--config',str(root/'config.json')],env=env,stdout=log,stderr=log,timeout=260)
 r=max((state/'runs').iterdir(),key=lambda p:p.name);summary=json.loads((r/'summary.json').read_text())
 if c.returncode or summary.get('stop_reason')!='recovery_check_complete':raise RuntimeError('Could not reach lobby')
 h=heartbeat()
 if not h['bound']:raise RuntimeError('Graphics interface unavailable')
 for label,fps in [('A1',20),('B',5),('A2',20)]:
  cmd.write_text(str(fps)+'\n'+(datetime.now(timezone.utc)+timedelta(seconds=110)).isoformat()+'\n')
  time.sleep(10);report('measuring',label=label,fps=fps)
  rows=[sample()]
  for i in range(12):time.sleep(5);rows.append(sample())
  if any(x['target_fps']!=fps or x['applied']!=fps for x in rows):raise RuntimeError('Target frame cap was not maintained')
  if len({x['pid'] for x in rows})!=1 or len({x['invocation'] for x in rows})!=1:raise RuntimeError('Game restarted during comparison')
  seconds=rows[-1]['t']-rows[0]['t'];r=dict(label=label,cap=fps,seconds=seconds,cpu_one_core_percent=(rows[-1]['cpu_us']-rows[0]['cpu_us'])/seconds/10000,render_fps=(rows[-1]['frames']-rows[0]['frames'])/seconds,memory_mib=rows[-1]['memory']/1048576,swap_mib=rows[-1]['swap']/1048576)
  results.append(r);(out/(label+'.json')).write_text(json.dumps(rows));report('sample_complete',result=r)
 (out/'result.json').write_text(json.dumps(dict(scope='lobby_only_same_process_A_B_A',results=results),indent=2));report('comparison_complete',results=results)
except Exception as e:report('failed',error=str(e),results=results)
finally:
 cmd.unlink(missing_ok=True)
 if stopped:
  # Allow the live probe to restore the original cap before removing the loader.
  time.sleep(3)
  try:report('restoring',frame=heartbeat())
  except Exception:pass
 if changed:
  plugin.write_bytes((out/'original-plugin.bin').read_bytes());manifest.write_bytes((out/'original-manifest.json').read_bytes())
 drop.unlink(missing_ok=True)
 if owned:pause.unlink(missing_ok=True)
 ctl('daemon-reload')
 if stopped:
  # Existing supervisor and schedule are preserved. The running game can be reused.
  ctl('start','bg-bot.service')
 report('finished',comparison_complete=len(results)==3,controller_resumed=stopped)
