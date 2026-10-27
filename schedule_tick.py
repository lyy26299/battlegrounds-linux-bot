"""Start once per configured window. A manual service stop is not undone."""
from pathlib import Path
import subprocess,json,os
from datetime import datetime
from schedule_window import load_schedule,window_key,BEIJING

def main():
    os.umask(0o077)
    state=Path.home()/'.local/state/battlegrounds-bot'
    marker=state/'schedule-last-window.json'
    key=window_key(datetime.now(BEIJING),load_schedule())
    active=subprocess.run(['systemctl','--user','is-active','--quiet','bg-bot.service']).returncode==0
    if key is None:
        marker.unlink(missing_ok=True)
        if active:subprocess.run(['systemctl','--user','stop','bg-bot.service'],check=True,timeout=50)
        return
    if (state/'STOP').exists() or (state/'PAUSE').exists():return
    try:last=json.loads(marker.read_text()).get('window')
    except (OSError,ValueError):last=None
    if last==key:return
    if not active:
        subprocess.run(['systemctl','--user','reset-failed','bg-bot.service'],check=True)
        subprocess.run(['systemctl','--user','start','bg-bot.service'],check=True,timeout=50)
    temp=marker.with_suffix('.tmp');temp.write_text(json.dumps({'window':key}));temp.replace(marker)
if __name__=='__main__':main()
