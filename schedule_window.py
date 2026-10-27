from datetime import datetime, timezone, timedelta
from pathlib import Path
import json,re,os,tempfile,time
BEIJING = timezone(timedelta(hours=8))
CONFIG=Path.home()/'.local/state/bg-dashboard/schedule.json'
DEFAULT={'start':'01:00','end':'12:00','enabled':True}
_cache={'at':0,'data':None}
def validate_schedule(data):
    if not isinstance(data,dict) or set(data)!={'start','end','enabled'}:raise ValueError('请填写开始时间、结束时间和启用状态')
    if type(data['enabled']) is not bool:raise ValueError('启用状态无效')
    for k in ('start','end'):
        if not isinstance(data[k],str) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',data[k]):raise ValueError('时间格式应为 HH:MM')
    if data['start']==data['end']:raise ValueError('开始和结束时间不能相同')
    return dict(data)
def load_schedule(path=None):
    path=Path(path) if path is not None else CONFIG
    try:return validate_schedule(json.loads(path.read_text()))
    except FileNotFoundError:return dict(DEFAULT)
    except (OSError,ValueError,TypeError):return dict(DEFAULT,enabled=False)
def current_schedule():
    if _cache['data'] is None or time.monotonic()-_cache['at']>=1:
        _cache.update(at=time.monotonic(),data=load_schedule())
    return _cache['data']
def save_schedule(data,path=None):
    data=validate_schedule(data);path=Path(path) if path is not None else CONFIG
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,temp=tempfile.mkstemp(prefix='.schedule-',dir=path.parent)
    try:
        with os.fdopen(fd,'w') as f:json.dump(data,f);f.flush();os.fsync(f.fileno())
        os.replace(temp,path)
    finally:
        if os.path.exists(temp):os.unlink(temp)
    _cache['at']=0
    return data
def inside_window(now=None,schedule=None):
    now=(now or datetime.now(BEIJING)).astimezone(BEIJING)
    s=current_schedule() if schedule is None else schedule
    if not s['enabled']:return False
    current=now.strftime('%H:%M');a,b=s['start'],s['end']
    return a<=current<b if a<b else current>=a or current<b
def window_key(now,schedule):
    if not inside_window(now,schedule):return None
    day=now.astimezone(BEIJING).date()
    if schedule['start']>schedule['end'] and now.astimezone(BEIJING).strftime('%H:%M')<schedule['end']:day-=timedelta(days=1)
    return f"{day}:{schedule['start']}:{schedule['end']}"
def parse_deadline(value):
    deadline=datetime.fromisoformat(value)
    if deadline.tzinfo is None:raise ValueError('Extra window deadline must include a timezone')
    return deadline
def running_window(now=None,extra_until=None):
    now=now or datetime.now(BEIJING)
    return inside_window(now) or (extra_until is not None and now<extra_until)
