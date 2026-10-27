"""Read-only readiness report. Does not launch the game or inspect credentials."""
import importlib.util
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

if __name__=='__main__':
    checks={
        'linux_x86_64':sys.platform=='linux' and platform.machine()=='x86_64',
        'python_3_10_to_3_12':(3,10)<=sys.version_info[:2]<(3,13),
        'display_configured':bool(os.environ.get('DISPLAY')),
    }
    for name in ('Xvfb','xauth','xdpyinfo','xprop','openbox','dbus-run-session'):
        checks[name]=bool(shutil.which(name))
    for name in ('Xlib','mss','cv2','numpy','PIL','rapidocr_onnxruntime'):
        checks['module_'+name]=importlib.util.find_spec(name) is not None
    path=Path(__file__).with_name('config.json')
    checks['config_exists']=path.exists()
    if path.exists():
        cfg=json.loads(path.read_text())
        for name in ('launcher','game_executable'):
            p=Path(cfg.get(name,'')).expanduser()
            checks[name]=p.is_file() and os.access(p,os.X_OK)
    print(json.dumps(checks,indent=2))
    if checks['display_configured'] and checks['xdpyinfo']:
        p=subprocess.run(['xdpyinfo'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        checks['display_reachable']=p.returncode==0
        print('display_reachable:',checks['display_reachable'])
    raise SystemExit(0 if all(checks.values()) else 1)
