"""Dedicated persistent X11 display. No public display or VNC port is opened."""
import os
from pathlib import Path
import secrets
import signal
import subprocess
import threading
import time


def write_openbox_config(path):
    """One workspace prevents accidental switches to an empty virtual desktop."""
    path = Path(path)
    path.write_text('''<?xml version="1.0" encoding="UTF-8"?>
<openbox_config xmlns="http://openbox.org/3.4/rc">
  <focus><focusNew>yes</focusNew><followMouse>no</followMouse></focus>
  <desktops><number>1</number><firstdesk>1</firstdesk></desktops>
  <keyboard><keybind key="A-Tab"><action name="NextWindow"/></keybind></keyboard>
  <mouse><context name="Titlebar"><mousebind button="Left" action="Press">
    <action name="Focus"/><action name="Raise"/>
  </mousebind></context></mouse>
</openbox_config>
''', encoding='utf-8')
    path.chmod(0o600)
    return path


def main():
    if os.environ.get('DISPLAY')!=':91': raise RuntimeError('Dedicated session requires DISPLAY=:91')
    auth=Path(os.environ['XAUTHORITY']); auth.parent.mkdir(parents=True,exist_ok=True)
    if Path('/tmp/.X91-lock').exists(): raise RuntimeError('Display :91 is occupied; not taking over')
    auth.touch(mode=0o600,exist_ok=True); auth.chmod(0o600)
    subprocess.run(['xauth','-f',str(auth),'add',':91','.',secrets.token_hex(16)],check=True)
    stop=threading.Event()
    for sig in (signal.SIGINT,signal.SIGTERM): signal.signal(sig,lambda *_:stop.set())
    children=[]
    try:
        x=subprocess.Popen(['Xvfb',':91','-screen','0','1280x960x24','-nolisten','tcp','-auth',str(auth)])
        children.append(x)
        for _ in range(100):
            if x.poll() is not None: raise RuntimeError('Xvfb exited')
            if stop.is_set(): return
            if subprocess.run(['xdpyinfo'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0: break
            stop.wait(.1)
        else: raise RuntimeError('Xvfb readiness timeout')
        wm_config=write_openbox_config(auth.parent/'openbox.xml')
        children.append(subprocess.Popen(['dbus-run-session','--','openbox','--config-file',str(wm_config)]))
        for _ in range(100):
            p=subprocess.run(['xprop','-root','_NET_SUPPORTING_WM_CHECK'],capture_output=True,text=True)
            if 'window id #' in p.stdout: break
            if stop.is_set(): return
            stop.wait(.1)
        else: raise RuntimeError('Openbox readiness timeout')
        subprocess.run(['xset','s','off'],check=True)
        subprocess.run(['xset','s','noblank'],check=True)
        subprocess.run(['systemd-notify','--ready'],check=True)
        while not stop.wait(1):
            if any(p.poll() is not None for p in children): raise RuntimeError('X11 session component exited')
    finally:
        for p in reversed(children):
            if p.poll() is None:
                p.terminate()
                try:p.wait(timeout=5)
                except subprocess.TimeoutExpired:p.kill();p.wait()

if __name__=='__main__':
    os.umask(0o077)
    main()
