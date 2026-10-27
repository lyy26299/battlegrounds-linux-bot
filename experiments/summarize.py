"""Summarize service CPU deltas; reject restart boundaries and stale phase labels."""
import json,sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
rows=[json.loads(s) for s in Path(sys.argv[1]).read_text().splitlines()]
summary={};phases=defaultdict(lambda:defaultdict(lambda:{'cpu_seconds':0.,'wall_seconds':0.,'samples':0}))
for unit in ('bg-game.service','bg-bot.service'):
 cpu=wall=0.;count=0;memory=[];swap=[]
 for before,after in zip(rows,rows[1:]):
  a=before['units'].get(unit,{});b=after['units'].get(unit,{})
  dt=after['monotonic']-before['monotonic']
  if a.get('ActiveState')!='active' or b.get('ActiveState')!='active':continue
  if a.get('InvocationID')!=b.get('InvocationID') or not 0<dt<15:continue
  try:delta=(int(b['CPUUsageNSec'])-int(a['CPUUsageNSec']))/1e9
  except (KeyError,ValueError):continue
  if delta<0 or delta>dt*4:continue
  cpu+=delta;wall+=dt;count+=1
  try:memory.append(int(b['MemoryCurrent']));swap.append(int(b.get('memory.swap.current',0)))
  except (KeyError,ValueError):pass
  try:age=after['epoch']-datetime.fromisoformat(after['phase_at']).timestamp()
  except (KeyError,ValueError):continue
  if not 0<=age<=10:continue
  item=phases[after['phase']][unit];item['cpu_seconds']+=delta;item['wall_seconds']+=dt;item['samples']+=1
 summary[unit]={'cpu_seconds':round(cpu,2),'valid_seconds':round(wall,2),'cpu_percent_one_core':round(cpu/wall*100,2) if wall else None,'intervals':count,'memory_max_mib':round(max(memory,default=0)/2**20,1),'swap_max_mib':round(max(swap,default=0)/2**20,1)}
for phase,units in phases.items():
 for unit,item in units.items():item['cpu_percent_one_core']=round(item['cpu_seconds']/item['wall_seconds']*100,2)
print(json.dumps({'source':Path(sys.argv[1]).name,'samples':len(rows),'elapsed_seconds':round(rows[-1]['monotonic']-rows[0]['monotonic'],2) if rows else 0,'units':summary,'phases':dict(phases),'note':'Preliminary when fewer than 60 minutes or three full games; one-shot read-only development probes ran during this baseline.'},ensure_ascii=False,indent=2))
