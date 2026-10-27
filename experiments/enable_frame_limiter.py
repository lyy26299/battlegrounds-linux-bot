"""Install at a confirmed match boundary, roll back if heartbeat fails."""
import json,time,subprocess,hashlib,os,signal
def interrupted(*args):raise RuntimeError("Interrupted")
signal.signal(signal.SIGTERM,interrupted)
from pathlib import Path
os.umask(0o077)
home=Path.home();root=home/'BattlegroundsLinux';state=home/'.local/state/battlegrounds-bot'
bridge=state/'bridge';pause=state/'PAUSE';flag=bridge/'low-render.enabled'
out=state/'experiments/frame-limiter';out.mkdir(parents=True,exist_ok=True)
drop=home/'.config/systemd/user/bg-game.service.d/60-low-render.conf'
plugin=home/'.local/share/hearthstone-linux-gui/game/Bin/BepInEx/plugins/BattlegroundsShadow/ShadowBridge.dll'
manifest=plugin.parents[2]/'shadow-install-manifest.json'
def ctl(*args):subprocess.run(['systemctl','--user',*args],check=True,timeout=55)
def report(stage):
    (out/'status.json').write_text(json.dumps({'stage':stage,'epoch':time.time()}));print(stage,flush=True)
def safe():
    d=json.loads((state/'probe/state.json').read_text());s=d['state']
    if not 0<=time.monotonic()-d['monotonic']<3:return False
    return s.get('available') and (s.get('m_gameOver') is True or (s.get('m_mode')==15 and s.get('m_sceneLoaded') and not s.get('m_transitioning')))
owned=False;stopped=False;changed=False;success=False
old_flag=flag.exists()
old_drop=drop.read_bytes() if drop.exists() else None
cap=bridge/'frame-cap.txt'
old_cap=cap.read_bytes() if cap.exists() else None
try:
    if pause.exists() or (state/'STOP').exists():raise RuntimeError('Existing maintenance or stop')
    report('waiting_for_match_boundary')
    until=time.monotonic()+1800
    while time.monotonic()<until:
        if (state/'STOP').exists() or pause.exists():raise RuntimeError('User stopped or paused')
        try:ready=safe()
        except (OSError,ValueError,KeyError):ready=False
        if ready:
            pause.touch(exist_ok=False);owned=True;time.sleep(1)
            if safe():break
            pause.unlink();owned=False
        time.sleep(.5)
    else:raise RuntimeError('No safe boundary')
    report('installing')
    ctl('stop','bg-bot');stopped=True;ctl('stop','bg-game')
    (out/'plugin-before.bin').write_bytes(plugin.read_bytes());(out/'manifest-before.json').write_bytes(manifest.read_bytes());changed=True
    plugin.write_bytes((root/'experiments/FrameLimiter.dll').read_bytes())
    m=json.loads(manifest.read_text());m['files']['BepInEx/plugins/BattlegroundsShadow/ShadowBridge.dll']=hashlib.sha256(plugin.read_bytes()).hexdigest();manifest.write_text(json.dumps(m))
    flag.unlink(missing_ok=True);cap.write_text('5\n');drop.parent.mkdir(parents=True,exist_ok=True)
    drop.write_text('[Service]\nExecStart=\nExecStart=/home/ubuntu/BattlegroundsLinux/.venv/bin/python /home/ubuntu/BattlegroundsLinux/state_host_low_render.py\n')
    ctl('daemon-reload');began=time.time();ctl('start','bg-game')
    for _ in range(120):
        try:
            p=bridge/'frame-test.json';s=json.loads(p.read_text())
            if p.stat().st_mtime>began and s.get('updates',0)>5 and s.get('target_fps')==5 and s.get('applied')==5 and not s.get('error') and Path('/proc/'+str(s['pid'])).exists():success=True;break
        except (OSError,ValueError,KeyError):pass
        time.sleep(1)
    if not success:raise RuntimeError('No fresh plugin heartbeat')
    report('installed')
finally:
    if changed and not success:
        ctl('stop','bg-game');plugin.write_bytes((out/'plugin-before.bin').read_bytes());manifest.write_bytes((out/'manifest-before.json').read_bytes());drop.write_bytes(old_drop) if old_drop is not None else drop.unlink(missing_ok=True)
        if old_flag:flag.touch()
        else:flag.unlink(missing_ok=True)
        if old_cap is None:cap.unlink(missing_ok=True)
        else:cap.write_bytes(old_cap)
        ctl('daemon-reload');report('rolled_back')
    if owned:pause.unlink(missing_ok=True)
    if stopped and not (state/'STOP').exists():ctl('start','bg-bot')
