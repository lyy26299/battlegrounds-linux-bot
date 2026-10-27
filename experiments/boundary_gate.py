"""One-shot match-boundary lease; auto-resume if nobody claims it in 60 seconds."""
import json,os,time,sys,subprocess
from pathlib import Path
from datetime import datetime,timezone
os.umask(0o077)
state=Path.home()/'.local/state/battlegrounds-bot'
run=max((state/'runs').iterdir(),key=lambda p:p.name)
path=run/'events.jsonl';pause=state/'PAUSE';lease=state/'experiments/boundary-lease.json';ack=state/'experiments/boundary-claimed'
if pause.exists():raise SystemExit('Existing pause is not owned by this gate')
ack.unlink(missing_ok=True)
deadline=time.monotonic()+1800
with path.open() as f:
 f.seek(0,2)
 while time.monotonic()<deadline:
  line=f.readline()
  if not line:
   if (run/'summary.json').exists():raise SystemExit('Controller ended before boundary')
   time.sleep(.2);continue
  try:event=json.loads(line)
  except ValueError:continue
  if event.get('observation',{}).get('phase')!='result':continue
  if (datetime.now(timezone.utc)-datetime.fromisoformat(event['time'])).total_seconds()>2:continue
  pause.touch(exist_ok=False)
  lease.write_text(json.dumps({'run':run.name,'epoch':time.time(),'expires':time.time()+60,'phase':'result'}))
  print('Match ended; controller paused at result for at most 60 seconds',flush=True)
  if '--cutover' in sys.argv:
   result=subprocess.run([sys.executable,str(Path(__file__).with_name('cutover_shadow.py'))],timeout=480)
   if result.returncode==0:break
  try:
   until=time.monotonic()+60
   while time.monotonic()<until:
    if ack.exists():print('Lease claimed for cutover',flush=True);break
    time.sleep(.5)
  finally:
   if not ack.exists():pause.unlink(missing_ok=True);lease.unlink(missing_ok=True);print('No claim; controller resumed',flush=True)
  break
 else:print('No boundary before timeout; no changes made',flush=True)
