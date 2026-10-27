"""Offline P1 diagnostics. Agreement alone never enables gameplay controls."""
import argparse,bisect,json,collections
from datetime import datetime,timedelta
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('shadow',type=Path);p.add_argument('events',type=Path);a=p.parse_args()
def read(path):
 out=[]
 for line in path.read_text().splitlines():
  try:out.append(json.loads(line))
  except ValueError:continue
 return out
shadow=read(a.shadow);events=read(a.events)
shadow.sort(key=lambda x:x['utc']);times=[datetime.fromisoformat(x['utc'].replace('Z','+00:00')).timestamp() for x in shadow]
report={'snapshots':len(shadow),'available':sum(bool(x.get('available')) for x in shadow),'errors':dict(collections.Counter(x.get('reason') for x in shadow if not x.get('available'))),'control_enabled':any(x.get('control_allowed') for x in shadow),'gold_checks':0,'skipped_ambiguous_capture_time':0,'estimated_capture_times':0,'gold_matches':0,'gold_mismatches':[],'note':'Diagnostic only. OCR can be stale or wrong. Manual screen checks and full games remain required.'}
for e in events:
 obs=e.get('observation',{})
 if obs.get('phase')!='recruit' or obs.get('gold') is None:continue
 if e.get('capture_utc'):
  capture=datetime.fromisoformat(e['capture_utc']).timestamp()
 elif e.get('action'):
  # Legacy events are timestamped after mouse execution; action duration is unknown.
  report['skipped_ambiguous_capture_time']+=1;continue
 else:
  capture=datetime.fromisoformat(e['time']).timestamp()-e.get('recognition_seconds',0)
  report['estimated_capture_times']+=1
 i=bisect.bisect_left(times,capture)
 candidates=[j for j in (i-1,i) if 0<=j<len(times)]
 if not candidates:continue
 j=min(candidates,key=lambda j:abs(times[j]-capture));s=shadow[j]
 if abs(times[j]-capture)>.4 or not s.get('available') or s.get('busy') or s.get('combat_tag')!=0:continue
 report['gold_checks']+=1
 if obs['gold']==s['gold_candidate']:report['gold_matches']+=1
 elif len(report['gold_mismatches'])<50:report['gold_mismatches'].append({'time':e['time'],'ocr':obs['gold'],'state':s['gold_candidate'],'turn':s['turn'],'delta_seconds':round(times[j]-capture,3)})
report['rates_by_session']={}
for session in sorted({x['session'] for x in shadow}):
 xs=[x for x in shadow if x['session']==session]
 if len(xs)<2:continue
 secs=(datetime.fromisoformat(xs[-1]['utc'].replace('Z','+00:00'))-datetime.fromisoformat(xs[0]['utc'].replace('Z','+00:00'))).total_seconds()
 if secs<=0:continue
 report['rates_by_session'][session]={'seconds':round(secs,2),'updates_per_second':round((xs[-1]['updates']-xs[0]['updates'])/secs,2),'rendered_frames_per_second':round((xs[-1]['rendered_frames']-xs[0]['rendered_frames'])/secs,2),'intervals':sorted({x['render_interval'] for x in xs}),'game_ids':len({x['game_id'] for x in xs if x.get('game_id')})}
print(json.dumps(report,ensure_ascii=False,indent=2))
