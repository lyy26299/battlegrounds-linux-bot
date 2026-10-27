"""Own the launched game and publish a private, read-only state snapshot.
No network listener or ptrace policy change. systemd owns this process group.
"""
import json,os,signal,subprocess,threading,time
from pathlib import Path
from datetime import datetime, timezone
from rewards import read_tracks
from mono_state import StateObserver,retain_game_parentage


def identity(pid):
    fields=Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()
    if fields[0]=='Z':raise ProcessLookupError('Game exited')
    return int(fields[19])


def descendant(pid):
    seen=set()
    while pid>1 and pid not in seen and len(seen)<128:
        seen.add(pid)
        pid=int(Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()[1])
        if pid==os.getpid():return True
    return False


def games(exe):
    for path in Path('/proc').glob('[0-9]*'):
        try:
            if path.stat().st_uid==os.getuid() and (path/'exe').resolve()==exe:
                pid=int(path.name);identity(pid);yield pid
        except (FileNotFoundError,ProcessLookupError,PermissionError):continue


def main():
    os.umask(0o077)
    cfg=json.loads(Path(__file__).with_name('config.json').read_text())
    exe=Path(cfg['game_executable']).expanduser().resolve(strict=True)
    if list(games(exe)):raise RuntimeError('Existing game must exit before starting state host')
    state=Path(cfg.get('state_dir','~/.local/state/battlegrounds-bot')).expanduser()/'probe'
    state.mkdir(parents=True,exist_ok=True,mode=0o700)
    retain_game_parentage()
    stop=threading.Event()
    for sig in (signal.SIGINT,signal.SIGTERM):signal.signal(sig,lambda *_:stop.set())
    with (state/'launcher-private.log').open('ab') as log:
        launcher=subprocess.Popen([str(Path(cfg['launcher']).expanduser()),'--launch'],stdout=log,stderr=log)
    observer=StateObserver();deadline=time.monotonic()+180;pid=None;birth=None;delay=.5
    boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    last_rewards=0
    try:
        while not stop.is_set():
            launcher.poll()
            if pid is None:
                candidates=[p for p in games(exe) if descendant(p)]
                if len(candidates)>1:raise RuntimeError('Multiple owned games')
                if candidates:pid=candidates[0];birth=identity(pid)
                else:
                    if time.monotonic()>deadline:raise RuntimeError('Game launch timed out')
                    stop.wait(.5);continue
            try:
                if identity(pid)!=birth:break
            except (FileNotFoundError,ProcessLookupError):break
            result={'pid':pid,'start_ticks':birth,'boot_id':boot,'monotonic':time.monotonic(),'state':observer.observe(pid)}
            if observer.memory and time.monotonic()-last_rewards>=10:
                last_rewards=time.monotonic()
                try:
                    tracks=read_tracks(observer.memory)
                    reward_data={'updated':datetime.now(timezone.utc).isoformat(),'pid':pid,'tracks':tracks}
                    reward_tmp=state/'rewards.tmp'
                    reward_tmp.write_text(json.dumps(reward_data));reward_tmp.replace(state/'rewards.json')
                except (OSError,ValueError,RuntimeError,KeyError):pass
            tmp=state/'state.tmp';tmp.write_text(json.dumps(result));tmp.replace(state/'state.json')
            delay=.5 if result['state'].get('available') else min(10,max(2,delay*2))
            stop.wait(delay)
    finally:
        observer.close()
        # Invalidate old state even when the service stops before game exit.
        (state/'state.json').unlink(missing_ok=True)


class FileObserver:
    def __init__(self,state_dir):
        self.path=Path(state_dir)/'probe/state.json'
        self.boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    last_rewards=0
    def observe(self,pid):
        try:
            data=json.loads(self.path.read_text())
            age=time.monotonic()-data['monotonic']
            if data['boot_id']!=self.boot or data['pid']!=pid or data['start_ticks']!=identity(pid) or not 0<=age<=3:
                return {'available':False,'reason':'stale_or_different_process'}
            return data['state']
        except (OSError,ValueError,KeyError,TypeError):
            return {'available':False,'reason':'state_host_unavailable'}
    def close(self):pass

if __name__=='__main__':main()
