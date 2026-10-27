"""Linux-only controller for hearthstone-linux-gui. Observe-only by default."""
import argparse
import copy
from dataclasses import asdict
from datetime import datetime
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
from core import Phase, Planner
from control import Lock, stale, interval, defer_transition_ocr
from recovery import RetryBudget, login_required, recovery_delay
from schedule_window import BEIJING, running_window, parse_deadline


def arguments():
    p=argparse.ArgumentParser()
    p.add_argument('--run',action='store_true')
    p.add_argument('--max-games',type=int,default=2)
    p.add_argument('--max-minutes',type=float,default=30)
    p.add_argument('--daily-window',action='store_true')
    p.add_argument('--extra-until',type=parse_deadline,help='One-time extra runtime ending at timezone-aware ISO datetime')
    p.add_argument('--auto-recover',action='store_true')
    p.add_argument('--recovery-check',action='store_true')
    probes=p.add_mutually_exclusive_group()
    probes.add_argument('--state-probe',action='store_true',help='Read-only Mono diagnostics for own game child')
    probes.add_argument('--state-host',action='store_true',help='Read private snapshots from persistent bg-game service')
    p.add_argument('--config',type=Path,default=Path(__file__).with_name('config.json'))
    a=p.parse_args()
    if a.max_games<0 or a.max_minutes<0: p.error('Limits must be nonnegative; 0 means unlimited')
    return a


def main():
    args=arguments()
    if args.daily_window and not running_window(extra_until=args.extra_until):
        print('Outside Beijing 01:00–12:00; no actions taken')
        return 0
    if sys.platform!='linux': raise RuntimeError('Live mode requires x86_64 Linux with X11')
    cfg=json.loads(args.config.read_text())
    launcher=Path(cfg['launcher']).expanduser().resolve(strict=True)
    game_exe=Path(cfg['game_executable']).expanduser().resolve(strict=True)
    if not os.access(launcher,os.X_OK): raise RuntimeError('Launcher is not executable')
    state=Path(cfg.get('state_dir','~/.local/state/battlegrounds-bot')).expanduser()
    with Lock(state/'controller.lock'):
        return run(args,launcher,game_exe,state)


def run(args,launcher,game_exe,state):
    from linux_backend import Desktop
    from vision import Detector
    from PIL import Image
    stamp=datetime.now(BEIJING).strftime('%Y%m%d-%H%M%S-%f')
    folder=state/'runs'/stamp; folder.mkdir(parents=True,exist_ok=True,mode=0o700)
    stop=threading.Event()
    for sig in (signal.SIGTERM,signal.SIGINT): signal.signal(sig,lambda *_:stop.set())
    began=time.monotonic()
    def allowed():
        return (not stop.is_set() and not (state/'STOP').exists() and
                (not args.daily_window or running_window(extra_until=args.extra_until)) and
                (not args.max_minutes or time.monotonic()-began<args.max_minutes*60))
    def paused(): return (state/'PAUSE').exists()
    def wait(n):
        until=time.monotonic()+n
        while allowed() and time.monotonic()<until: stop.wait(min(.1,until-time.monotonic()))
    def save(im,name): Image.fromarray(im).save(folder/name)
    detector=Detector()
    observer=None
    if args.state_probe:
        from mono_state import StateObserver,retain_game_parentage
        retain_game_parentage()
        observer=StateObserver()
    elif args.state_host:
        from state_host import FileObserver
        observer=FileObserver(state)
    desk=Desktop(game_exe)
    budget=RetryBudget()
    planner=Planner()
    loading_since=None
    disconnect_since=unknown_since=foreground_since=None
    last_phase=None
    error=None
    stop_reason='stopped'
    sequence=0
    last_full=last_skip_log=0.0
    log=(folder/'events.jsonl').open('a')
    launch_processes=[]
    def emit(event):
        event['time']=datetime.now(BEIJING).isoformat()
        log.write(json.dumps(event,ensure_ascii=False)+'\n'); log.flush()
    def recover(w=None):
        if not allowed() or paused(): return False
        budget.take()
        emit({'recovery':'restart' if w else 'launch'})
        if w: desk.close_game(w,stop,lambda: allowed() and not paused())
        if not allowed() or paused(): return False
        # Token/login handling stays inside the upstream launcher. Never copy credentials into logs.
        proc=None
        if args.state_host:
            subprocess.run(['systemctl','--user','restart','bg-game.service'],check=True,timeout=20)
        else:
            with (folder/'launcher-private.log').open('ab') as output:
                proc=subprocess.Popen([str(launcher),'--launch'],stdout=output,stderr=subprocess.STDOUT)
            launch_processes.append(proc)
        deadline=time.monotonic()+180
        while allowed() and time.monotonic()<deadline:
            if paused(): wait(.2); continue
            win=desk.find()
            if win: wait(5); return allowed()
            if proc is not None and proc.poll() is not None and proc.returncode!=0:
                raise RuntimeError('linux-gui launch failed; check local private log and complete login manually')
            wait(1)
        if allowed(): raise RuntimeError('Game window did not appear within 180 seconds; login may be required')
        return False
    print('Observe-only' if not args.run else 'Mouse control enabled',flush=True)
    print(f'Create {state}/STOP to stop, PAUSE to pause; SIGTERM also stops',flush=True)
    try:
        while allowed():
            if paused(): foreground_since=None; unknown_since=None; wait(.2); continue
            w=desk.find()
            if not w:
                if args.run and args.auto_recover:
                    if not recover(): break
                    foreground_since=unknown_since=None
                    continue
                raise RuntimeError('No visible game window for configured executable')
            if not desk.active(w):
                foreground_since=unknown_since=None
                wait(.2); continue
            foreground_since=foreground_since or time.monotonic()
            if time.monotonic()-foreground_since<3: wait(.2); continue
            mono_snapshot=None
            probe_elapsed=0.0
            if observer:
                probe_started=time.monotonic()
                mono_snapshot=observer.observe(w.pid)
                probe_elapsed=time.monotonic()-probe_started
                if defer_transition_ocr(mono_snapshot,time.monotonic()-last_full):
                    if time.monotonic()-last_skip_log>=2:
                        emit({'mono_state':mono_snapshot,'recognition_skipped':'scene_transition','probe_seconds':probe_elapsed})
                        last_skip_log=time.monotonic()
                    wait(.5);continue
            captured=time.monotonic()
            last_full=captured
            im=desk.image(w)
            obs=detector.observe(im)
            sequence+=1
            if login_required(''.join(obs.evidence)):
                raise RuntimeError('Login or verification required; complete it manually')
            if last_phase!=obs.phase:
                save(im,f'{sequence:06d}-{obs.phase.value}.png')
                last_phase=obs.phase
            if obs.phase==Phase.DISCONNECTED:
                disconnect_since=disconnect_since or time.monotonic()
                if args.run and args.auto_recover and time.monotonic()-disconnect_since>=recovery_delay(''.join(obs.evidence)):
                    if not recover(w): break
                    games=planner.games; planner=Planner(); planner.games=games
                    foreground_since=disconnect_since=unknown_since=None
                    continue
                if args.run and not args.auto_recover: raise RuntimeError('Disconnected; recovery disabled')
            else: disconnect_since=None
            if obs.phase==Phase.LOADING:
                loading_since=loading_since or time.monotonic()
                if time.monotonic()-loading_since>300:
                    raise RuntimeError('Game startup exceeded five minutes')
            else: loading_since=None
            if obs.phase==Phase.UNKNOWN:
                unknown_since=unknown_since or time.monotonic()
                if time.monotonic()-unknown_since>120: raise RuntimeError('Unrecognized screen for two minutes')
            else: unknown_since=None
            planner.record(obs)
            if obs.phase==Phase.LOBBY and (args.recovery_check or (args.max_games and planner.games>=args.max_games)):
                stop_reason='recovery_check_complete' if args.recovery_check else 'game_limit'
                emit({'stop_reason':stop_reason}); break
            previous=copy.copy(planner)
            action=planner.next(obs) if args.run and not stale(obs.seconds,time.monotonic()-captured) else None
            event={'observation':asdict(obs),'recognition_seconds':time.monotonic()-captured,
                   'action':asdict(action) if action else None}
            if observer:
                event['mono_state']=mono_snapshot
                event['probe_seconds']=probe_elapsed
            if action:
                # Recheck time, focus and geometry after OCR, and during every drag.
                event['executed']=False
                if not stale(obs.seconds,time.monotonic()-captured):
                    event['executed']=desk.perform(w,action,lambda: allowed() and not paused())
                if not event['executed']: planner=previous
                save(im,f'{sequence:06d}-before-action.png')
            emit(event)
            wait(interval(obs.phase,action))
    except Exception as exc:
        error=f'{type(exc).__name__}: {exc}'
        print(error,flush=True)
        try:
            w=desk.find()
            if w: save(desk.image(w),'stopped.png')
        except Exception: pass
    finally:
        stop.set()
        for proc in launch_processes:
            proc.poll()
        desk.close(); log.close()
        if observer: observer.close()
        summary={'games':planner.games,'error':error,'stop_reason':stop_reason,
                 'mode':'run' if args.run else 'observe','elapsed_seconds':time.monotonic()-began,
                 'experience_verified':False}
        (folder/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    return 1 if error else 0

if __name__=='__main__':
    os.umask(0o077)
    try: raise SystemExit(main())
    except (RuntimeError,FileNotFoundError,KeyError,ValueError) as exc:
        print(f'STOP: {exc}',file=sys.stderr); raise SystemExit(1)
