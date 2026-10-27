"""Bounded shutdown of the exact game owned by bg-game.service."""
import json,os,select,signal
from pathlib import Path

def owned(pid,exe,proc=Path('/proc')):
    p=proc/str(pid)
    return (p.stat().st_uid==os.getuid() and (p/'exe').resolve()==exe and
            any(line.endswith('/bg-game.service') for line in (p/'cgroup').read_text().splitlines()))

def main():
    cfg=json.loads(Path(__file__).with_name('config.json').read_text())
    exe=Path(cfg['game_executable']).expanduser().resolve(strict=True)
    for path in Path('/proc').glob('[0-9]*'):
        pid=int(path.name)
        try:
            if not owned(pid,exe):continue
            fd=os.pidfd_open(pid)
            try:
                if not owned(pid,exe):continue
                poll=select.poll();poll.register(fd,select.POLLIN)
                signal.pidfd_send_signal(fd,signal.SIGTERM)
                if not poll.poll(5000):
                    signal.pidfd_send_signal(fd,signal.SIGKILL)
                    if not poll.poll(5000):raise RuntimeError('Owned game did not exit after bounded shutdown')
            finally:os.close(fd)
        except (FileNotFoundError,ProcessLookupError,PermissionError):continue

if __name__=='__main__':main()
