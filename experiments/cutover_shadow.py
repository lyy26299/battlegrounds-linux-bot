"""Claim an end-of-game lease, try read-only loader, and resume original controller.
A failed load always restores the plain host. Experimental startup never persists
into the next scheduled run or a later recovery.
"""
import hashlib,json,os,shutil,subprocess,time
from pathlib import Path
os.umask(0o077)
home=Path.home();root=home/'BattlegroundsLinux';state=home/'.local/state/battlegrounds-bot'
lease_path=state/'experiments/boundary-lease.json';lease=json.loads(lease_path.read_text())
if not (state/'PAUSE').exists() or not 0<=time.time()-lease['epoch']<45:raise SystemExit('No fresh owned boundary lease')
if lease['run']!=max((state/'runs').iterdir(),key=lambda p:p.name).name:raise SystemExit('Run changed')
probe=json.loads((state/'probe/state.json').read_text())
if not 0<=time.monotonic()-probe['monotonic']<3 or not (probe['state'].get('m_gameOver') is True or probe['state'].get('m_mode')==15):raise SystemExit('Game has not confirmed an ended match')
(state/'experiments/boundary-claimed').touch()
shadow_drop=Path('/run/user/1000/systemd/user/bg-game.service.d/90-shadow.conf')
night_drop=Path('/run/user/1000/systemd/user/bg-bot.service.d/90-extra.conf')
def ctl(*args):subprocess.run(['systemctl','--user',*args],check=True,timeout=50)
loaded=False;reason='no_heartbeat';began=time.time()
try:
 ctl('stop','bg-bot.service');ctl('stop','bg-game.service')
 plugin=home/'.local/share/hearthstone-linux-gui/game/Bin/BepInEx/plugins/BattlegroundsShadow/ShadowBridge.dll'
 shutil.copy2(root/'experiments/bridge/ShadowBridge.dll',plugin)
 manifest=plugin.parents[2]/'shadow-install-manifest.json';data=json.loads(manifest.read_text())
 data['files']['BepInEx/plugins/BattlegroundsShadow/ShadowBridge.dll']=hashlib.sha256(plugin.read_bytes()).hexdigest();manifest.write_text(json.dumps(data,indent=2))
 shadow_drop.parent.mkdir(parents=True,exist_ok=True)
 shadow_drop.write_text('[Service]\nExecStart=\nExecStart=/home/ubuntu/BattlegroundsLinux/.venv/bin/python /home/ubuntu/BattlegroundsLinux/state_host_shadow.py\n')
 ctl('daemon-reload');(state/'PAUSE').unlink(missing_ok=True);ctl('start','bg-game.service')
 until=time.monotonic()+85
 while time.monotonic()<until:
  try:
   f=state/'bridge/shadow.json';snapshot=json.loads(f.read_text())
   if f.stat().st_mtime>began and snapshot.get('control_allowed') is False and snapshot.get('updates',0)>3:
    loaded=True;reason='readonly_heartbeat';print('Read-only component heartbeat confirmed',flush=True);break
  except (OSError,ValueError,TypeError):pass
  time.sleep(1)
 if loaded:
  env=dict(os.environ,DISPLAY=':91',XAUTHORITY=str(state/'Xauthority'))
  with (state/'experiments/login-validation.log').open('ab') as log:
   check=subprocess.run([str(root/'.venv/bin/python'),str(root/'runner_shadow.py'),'--shadow-observe','--run','--recovery-check','--state-host','--max-games','0','--max-minutes','3','--config',str(root/'config.json')],env=env,stdout=log,stderr=log,timeout=210)
  newest=max((state/'runs').iterdir(),key=lambda p:p.name)
  summary=json.loads((newest/'summary.json').read_text())
  loaded=check.returncode==0 and summary.get('stop_reason')=='recovery_check_complete'
  reason='lobby_and_observer_verified' if loaded else 'game_login_or_lobby_validation_failed'
 if not loaded:ctl('stop','bg-game.service')
except Exception as exc:
 reason=type(exc).__name__;loaded=False
 try:ctl('stop','bg-game.service')
 except Exception:pass
finally:
 # Even success is a one-launch experiment; future restarts use the plain host.
 shadow_drop.unlink(missing_ok=True);(state/'PAUSE').unlink(missing_ok=True)
 night_drop.parent.mkdir(parents=True,exist_ok=True)
 command='runner_shadow.py --shadow-observe' if loaded else 'runner.py'
 night_drop.write_text('[Service]\nExecStart=\nExecStart=/home/ubuntu/BattlegroundsLinux/.venv/bin/python /home/ubuntu/BattlegroundsLinux/'+command+' --run --auto-recover --state-host --daily-window --max-games 0 --max-minutes 0 --config /home/ubuntu/BattlegroundsLinux/config.json --extra-until 2026-10-26T01:00:00+08:00\n')
 try:
  ctl('daemon-reload');ctl('reset-failed','bg-bot.service');ctl('start','bg-bot.service')
 finally:
  night_drop.unlink(missing_ok=True);ctl('daemon-reload');lease_path.unlink(missing_ok=True)
 (state/'experiments/shadow-cutover-result.json').write_text(json.dumps({'loaded':loaded,'reason':reason,'epoch':time.time(),'actions_enabled':False,'render_changes_enabled':False}))
 print(json.dumps({'loaded':loaded,'reason':reason,'controller_resumed':True}),flush=True)
