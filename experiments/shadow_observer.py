"""Private snapshot reader; invalid or expired files supply no decision data."""
import json,os,stat,time
from datetime import datetime,timezone
from pathlib import Path
class ShadowObserver:
 def __init__(self,path):self.path=Path(path);self.previous=None
 def read(self,pid):
  try:
   fd=os.open(self.path,os.O_RDONLY|os.O_NOFOLLOW)
   try:
    info=os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_mode&0o077 or info.st_size>65536:return None
    raw=os.read(fd,65537)
   finally:os.close(fd)
   data=json.loads(raw)
   timestamp=datetime.fromisoformat(data['utc'].replace('Z','+00:00')).timestamp()
   if not 0<=time.time()-timestamp<=1.5 or data['pid']!=pid:return None
   if not isinstance(data['session'],str) or len(data['session'])!=32:return None
   if data.get('control_allowed') is not False:return None
   return data
  except (OSError,ValueError,KeyError,TypeError,AttributeError):return None
 def pair(self,pid):
  current=self.read(pid);previous=self.previous;self.previous=current
  return previous,current
