"""Read-only comparison of fresh observer snapshots with existing controller events."""
import json,time,os
from pathlib import Path
from datetime import datetime,timezone
os.umask(0o077)
state=Path.home()/'.local/state/battlegrounds-bot';source=state/'bridge/shadow.json'
out=state/'experiments/shadow-health.jsonl'
last=None
with out.open('a') as log:
 for _ in range(240):
  try:
   s=json.loads(source.read_text());age=(datetime.now(timezone.utc)-datetime.fromisoformat(s['utc'].replace('Z','+00:00'))).total_seconds()
   fresh=0<=age<2
   row={'utc':datetime.now(timezone.utc).isoformat(),'fresh':fresh,'available':s.get('available'),'reason':s.get('reason'),'render_interval':s.get('render_interval'),'control_allowed':s.get('control_allowed')}
   if fresh and last and s['session']==last['session']:
    dt=(datetime.fromisoformat(s['utc'].replace('Z','+00:00'))-datetime.fromisoformat(last['utc'].replace('Z','+00:00'))).total_seconds()
    if dt>0:
     row['logic_hz']=(s['updates']-last['updates'])/dt;row['render_hz']=(s['rendered_frames']-last['rendered_frames'])/dt
   if fresh:last=s
   log.write(json.dumps(row)+'\n');log.flush()
  except (OSError,ValueError,KeyError,TypeError):pass
  time.sleep(5)
