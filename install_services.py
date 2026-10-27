"""Generate user systemd units. Preview by default; enable only after live acceptance."""
import argparse
from pathlib import Path
import subprocess
import sys


def quoted(path):
    text=str(path)
    if '\n' in text or '\r' in text: raise ValueError('Invalid path')
    return '"'+text.replace('\\','\\\\').replace('"','\\"').replace('%','%%')+'"'


def units(root):
    python=quoted(root/'.venv/bin/python')
    # WorkingDirectory is a single path value, not an ExecStart word list.
    directory=str(root).replace('%','%%')
    if '\n' in directory or '\r' in directory: raise ValueError('Invalid directory')
    common='Environment=DISPLAY=:91\nEnvironment=XAUTHORITY=%h/.local/state/battlegrounds-bot/Xauthority\n'
    session=f'''[Unit]
Description=Persistent Hearthstone X11 desktop
[Service]
Type=notify
NotifyAccess=all
{common}ExecStart={python} {quoted(root/'session.py')}
Restart=on-failure
RestartSec=15
TimeoutStartSec=30
UMask=0077
[Install]
WantedBy=default.target
'''
    bot=f'''[Unit]
Description=Battlegrounds daily controller
OnFailure=bg-attention.service
Requires=bg-desktop.service
After=bg-desktop.service
[Service]
Type=simple
{common}WorkingDirectory={directory}
ExecStart={python} {quoted(root/'runner.py')} --run --auto-recover --state-host --daily-window --max-games 0 --max-minutes 0 --config {quoted(root/'config.json')}
ExecStopPost=/usr/bin/systemctl --user stop bg-game.service
Restart=no
TimeoutStopSec=45
KillMode=process
UMask=0077
'''
    # Daily controller cleanup stops its owned game host; desktop remains available.
    # No automatic restart after an error: preserve retry limits and the failure evidence.
    timer='''[Unit]
Description=Start Battlegrounds at 01:00 Beijing time
[Timer]
OnCalendar=*-*-* 01:00:00 Asia/Shanghai
Persistent=true
AccuracySec=1s
Unit=bg-bot.service
[Install]
WantedBy=timers.target
'''
    game=f'''[Unit]
Description=Owned Hearthstone game and private state reader
Requires=bg-desktop.service
After=bg-desktop.service
[Service]
Type=simple
{common}WorkingDirectory={directory}
ExecStart={python} {quoted(root/'state_host.py')}
ExecStop={python} {quoted(root/'stop_game.py')}
Restart=no
KillMode=control-group
TimeoutStopSec=20
UMask=0077
'''
    attention=f"""[Unit]
Description=Show stopped automation notice on the private desktop
Requires=bg-desktop.service
After=bg-desktop.service
[Service]
{common}ExecStart=/usr/bin/xmessage -center -title "Battlegrounds needs attention" -buttons OK:0 -default OK -file {quoted(root/'attention.txt')}
Restart=no
UMask=0077
"""
    return {'bg-attention.service':attention,'bg-desktop.service':session,'bg-game.service':game,'bg-bot.service':bot,'bg-bot.timer':timer}

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--write',action='store_true')
    p.add_argument('--enable',action='store_true',help='Only after two-game and disconnect acceptance')
    a=p.parse_args()
    if a.enable and not a.write:p.error('--enable requires --write')
    root=Path(__file__).resolve().parent
    if a.write and sys.platform!='linux':p.error('Install only on Linux')
    if a.write and not (root/'config.json').exists():p.error('Create and check config.json first')
    directory=Path.home()/'.config/systemd/user'
    for name,text in units(root).items():
        if a.write:
            directory.mkdir(parents=True,exist_ok=True);(directory/name).write_text(text)
        else:print(f'--- {name} ---\n{text}')
    if a.write:
        subprocess.run(['systemctl','--user','daemon-reload'],check=True)
    if a.enable:
        subprocess.run(['systemctl','--user','enable','--now','bg-desktop.service','bg-bot.timer'],check=True)
