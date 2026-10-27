"""Validated low-render startup; incompatible installs use the normal host."""
import json, runpy
from pathlib import Path
from experiments.loader_environment import game_environment
root=Path(__file__).resolve().parent
state=Path.home()/'.local/state/battlegrounds-bot'
host='state_host.py'
if (state/'bridge/low-render.enabled').exists() or (state/'bridge/frame-cap.txt').exists():
    try:
        cfg=json.loads((root/'config.json').read_text())
        game_environment(Path(cfg['game_executable']).expanduser())
        host='state_host_shadow.py'
    except (OSError,ValueError,KeyError,RuntimeError):
        print('Low-render validation unavailable; using normal host',flush=True)
runpy.run_path(str(root/host),run_name='__main__')
