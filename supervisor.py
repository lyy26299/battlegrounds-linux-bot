"""Recover known controller stalls without overriding manual stops or schedules."""
import json,os,signal,subprocess,sys,threading,time
from pathlib import Path
from schedule_window import running_window

RECOVERABLE=('同一操作连续无效','Unrecognized screen for two minutes','Game startup exceeded five minutes','30分钟内已尝试恢复3次')
def recoverable(summary):
    error=summary.get('error') or ''
    return any(message in error for message in RECOVERABLE)

def recovery_loop(launch, permitted, wait, close_game, report):
    failures=0
    while permitted():
        code,summary=launch()
        if not permitted():return 0
        if code==0:return 0
        if not recoverable(summary):
            report('needs_attention',error=summary.get('error','Controller failed without summary'))
            return code
        failures=0 if summary.get('elapsed_seconds',0)>=1800 else failures
        failures+=1
        # Three staggered retries, then a long cooldown; never rapid infinite restarts.
        delay=(30,120,300)[failures-1] if failures<=3 else 1800
        report('cooldown',attempt=failures,delay_seconds=delay,error=summary.get('error'))
        close_game()
        wait(delay)
    return 0

def main():
    os.umask(0o077)
    root=Path(__file__).resolve().parent
    cfg=json.loads((root/'config.json').read_text())
    state=Path(cfg.get('state_dir','~/.local/state/battlegrounds-bot')).expanduser()
    stop=threading.Event();child=None
    def terminate(*_):
        stop.set()
        if child is not None and child.poll() is None:child.send_signal(signal.SIGTERM)
    for sig in (signal.SIGTERM,signal.SIGINT):signal.signal(sig,terminate)
    def permitted():return not stop.is_set() and not (state/'STOP').exists() and running_window()
    def report(status,**details):
        data=dict(status=status,updated_epoch=time.time(),**details)
        temp=state/'recovery-status.tmp';temp.write_text(json.dumps(data,ensure_ascii=False));temp.replace(state/'recovery-status.json')
        print(json.dumps(data,ensure_ascii=False),flush=True)
    def wait(seconds):
        until=time.monotonic()+seconds
        while permitted() and (time.monotonic()<until or (state/'PAUSE').exists()):stop.wait(.25)
    def close_game():
        subprocess.run(['systemctl','--user','stop','bg-game.service'],check=True,timeout=40)
    def launch():
        nonlocal child
        while permitted() and (state/'PAUSE').exists():stop.wait(.25)
        if not permitted():return 0,{}
        runs=state/'runs';before=set(runs.iterdir()) if runs.exists() else set()
        report('running')
        child=subprocess.Popen([sys.executable,str(root/'runner.py'),'--run','--auto-recover','--state-host','--daily-window','--max-games','0','--max-minutes','0','--config',str(root/'config.json')])
        try:
            while child.poll() is None:
                if not permitted():
                    child.terminate()
                    try:child.wait(timeout=35)
                    except subprocess.TimeoutExpired:child.kill();child.wait()
                    break
                stop.wait(.25)
            code=child.returncode
        finally:
            if child.poll() is None:child.terminate();child.wait(timeout=35)
            child=None
        fresh=set(runs.iterdir())-before if runs.exists() else set()
        if len(fresh)!=1:return code,{'error':'No unambiguous new controller summary'}
        try:summary=json.loads((fresh.pop()/'summary.json').read_text())
        except (OSError,ValueError):summary={'error':'Controller summary unavailable'}
        return code,summary
    result=recovery_loop(launch,permitted,wait,close_game,report)
    if result==0:report('stopped')
    return result

if __name__=='__main__':raise SystemExit(main())
