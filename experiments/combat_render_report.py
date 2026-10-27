"""Summarize fresh same-process rendering samples; no causal claim across scenes."""
import json,sys,statistics
from datetime import datetime
rows=[json.loads(l) for l in open(sys.argv[1])]
groups={}
for a,b in zip(rows,rows[1:]):
    x=a.get('shadow',{});y=b.get('shadow',{})
    try:
        age=b['epoch']-datetime.fromisoformat(y['utc'].replace('Z','+00:00')).timestamp()
        if not 0<=age<4 or x['pid']!=y['pid'] or x['session']!=y['session'] or x['render_interval']!=y['render_interval']:continue
        u=a['units']['bg-game.service'];v=b['units']['bg-game.service']
        if u['InvocationID']!=v['InvocationID']:continue
        dt=b['monotonic']-a['monotonic']
        item={'cpu_machine_percent':(int(v['CPUUsageNSec'])-int(u['CPUUsageNSec']))/1e9/dt*50,'render_fps':(y['rendered_frames']-x['rendered_frames'])/dt,'update_fps':(y['updates']-x['updates'])/dt,'memory_mib':int(v['MemoryCurrent'])/1048576}
        groups.setdefault(str(y['render_interval']),[]).append(item)
    except (KeyError,ValueError,TypeError):continue
print(json.dumps({k:{'samples':len(v),**{m:round(statistics.mean(i[m] for i in v),2) for m in v[0]}} for k,v in groups.items()},ensure_ascii=False,indent=2))
