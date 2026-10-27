"""Private local transport. A timeout means unknown outcome, never safe to resend."""
import json,os,socket,stat,time,uuid
from pathlib import Path
class UnknownOutcome(RuntimeError):pass

def command(path,action,*,session,game_id,turn,options_id,entity_id,position=0,timeout=3):
    if action not in ('buy','play','sell','choose'):raise ValueError('Unsupported action')
    path=Path(path);mode=path.stat()
    if not stat.S_ISSOCK(mode.st_mode) or mode.st_uid!=os.getuid() or mode.st_mode&0o077:
        raise PermissionError('Bridge socket is not private to the current user')
    message={'version':1,'id':uuid.uuid4().hex,'session':session,'action':action,'gameId':game_id,'turn':turn,'optionsId':options_id,'entityId':entity_id,'position':position,'expiresMs':int((time.time()+timeout)*1000)}
    data=json.dumps(message,separators=(',',':')).encode()+b'\n'
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as conn:
        conn.settimeout(timeout)
        conn.connect(str(path))
        try:
            conn.sendall(data);response=b''
            while b'\n' not in response:
                part=conn.recv(4096)
                if not part:raise UnknownOutcome('Bridge disconnected; observe state before doing anything else')
                response+=part
                if len(response)>16384:raise UnknownOutcome('Oversized bridge response')
            result=json.loads(response.split(b'\n',1)[0])
            if result.get('id')!=message['id']:raise UnknownOutcome('Mismatched response identity')
            if result.get('status')=='unknown':raise UnknownOutcome('Handler outcome unknown; re-observe, do not resend')
            return result
        except (socket.timeout,OSError,ValueError) as exc:
            raise UnknownOutcome('Action outcome unknown; re-observe, do not blindly resend') from exc
