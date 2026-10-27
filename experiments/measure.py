"""Read-only service-group baseline, resilient to game and controller restarts."""
import json,time,subprocess,os,argparse
os.umask(0o077)
parser=argparse.ArgumentParser()
parser.add_argument("--seconds",type=int,default=3605)
args=parser.parse_args()
if args.seconds<5:parser.error("At least five seconds required")
from pathlib import Path
state=Path.home()/'.local/state/battlegrounds-bot'
out=state/'experiments';out.mkdir(exist_ok=True)
path=out/('baseline-'+time.strftime('%Y%m%d-%H%M%S')+'.jsonl')
def sample_unit(name):
 text=subprocess.check_output(['systemctl','--user','show',name,'-p','CPUUsageNSec','-p','MemoryCurrent','-p','ControlGroup','-p','InvocationID','-p','ActiveState'],text=True,timeout=3)
 d=dict(line.split('=',1) for line in text.splitlines());group=Path('/sys/fs/cgroup')/d['ControlGroup'].lstrip('/')
 for name in ['memory.swap.current','memory.events']:
  try:d[name]= (group/name).read_text().strip()
  except OSError:pass
 return d
with path.open('x') as f:
 began=time.monotonic()
 for i in range(args.seconds//5+2):
  if i and time.monotonic()-began>args.seconds+5:break
  start=time.monotonic();row={'epoch':time.time(),'monotonic':start,'sample':i,'units':{}}
  for name in ['bg-game.service','bg-bot.service']:
   try:row['units'][name]=sample_unit(name)
   except Exception as e:row['units'][name]={'error':type(e).__name__}
  try:
   run=max((state/'runs').iterdir(),key=lambda p:p.name)
   row['run']=run.name
   with (run/'events.jsonl').open('rb') as log:
    log.seek(0,2);log.seek(max(0,log.tell()-30000));lines=log.read().splitlines()[1:]
   for line in reversed(lines):
    try:e=json.loads(line)
    except ValueError:continue
    if e.get('observation'):
     row['phase']=e['observation']['phase'];row['phase_at']=e['time'];break
  except (OSError,ValueError):pass
  try:
   shadow=json.loads((state/'bridge/shadow.json').read_text())
   row['shadow']={k:shadow.get(k) for k in ('utc','pid','session','updates','rendered_frames','render_interval','target_fps','vsync','available','game_id','turn','busy')}
  except (OSError,ValueError,TypeError):pass
  f.write(json.dumps(row)+'\n');f.flush()
  time.sleep(max(0,5-(time.monotonic()-start)))
print(path,flush=True)
