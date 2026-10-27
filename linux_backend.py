"""X11 screenshot/input adapter. Requires a persistent Xorg/Xvfb session.
Only controls one visible window belonging to the explicitly configured binary.
"""
from dataclasses import dataclass
from pathlib import Path
import os
import subprocess
import time

@dataclass(frozen=True)
class Window:
    xid: int
    pid: int
    left: int
    top: int
    width: int
    height: int

    def point(self, p):
        if p is None or not (.02 < p[0] < .98 and .02 < p[1] < .98):
            raise ValueError('Coordinate outside allowed game area')
        return self.left+round(p[0]*self.width), self.top+round(p[1]*self.height)


def validate_window(w, screen_width, screen_height):
    if w.width < 800 or w.height < 600 or abs(w.width/w.height-4/3) > .025:
        raise RuntimeError('Set Hearthstone to 1024x768, 4:3, before running')
    if w.left < 0 or w.top < 0 or w.left+w.width > screen_width or w.top+w.height > screen_height:
        raise RuntimeError('Game window is outside the captured desktop')


class Desktop:
    def __init__(self, game_exe):
        if not os.environ.get('DISPLAY'):
            raise RuntimeError('DISPLAY missing; start the persistent X11 session')
        from Xlib import display, X, Xatom
        from Xlib.ext import xtest
        import mss
        self.X, self.Xatom, self.xtest = X, Xatom, xtest
        self.d = display.Display()
        self.root = self.d.screen().root
        self.capture = mss.mss()
        self.game_exe = Path(game_exe).expanduser().resolve(strict=True)

    def prop(self, win, name):
        p = win.get_full_property(self.d.intern_atom(name), self.X.AnyPropertyType)
        return None if p is None else p.value

    def find(self):
        ids = self.prop(self.root, '_NET_CLIENT_LIST')
        if ids is None:
            raise RuntimeError('No EWMH window manager; start Openbox in the X11 session')
        found=[]
        for xid in ids:
            win=self.d.create_resource_object('window', int(xid))
            try:
                pid=self.prop(win, '_NET_WM_PID')
                if pid is None: continue
                pid=int(pid[0])
                if Path(f'/proc/{pid}').stat().st_uid != os.getuid(): continue
                if Path(f'/proc/{pid}/exe').resolve() != self.game_exe: continue
                title=self.prop(win, '_NET_WM_NAME')
                if title is None: title=win.get_wm_name() or ''
                if isinstance(title,bytes): title=title.decode('utf-8','replace')
                if str(title).strip() not in ('Hearthstone','炉石传说'): continue
                if win.get_attributes().map_state != self.X.IsViewable: continue
                g=win.get_geometry()
                pos=self.root.translate_coords(win, 0, 0)
                item=Window(int(xid),pid,pos.x,pos.y,g.width,g.height)
                screen=self.root.get_geometry()
                validate_window(item,screen.width,screen.height)
                found.append(item)
            except (FileNotFoundError, ProcessLookupError):
                continue
        if len(found)>1: raise RuntimeError('More than one Hearthstone window')
        return found[0] if found else None

    def active(self, w):
        p=self.prop(self.root,'_NET_ACTIVE_WINDOW')
        return p is not None and int(p[0])==w.xid and self.find()==w

    def image(self,w):
        import numpy as np
        return np.asarray(self.capture.grab(dict(left=w.left,top=w.top,width=w.width,height=w.height)))[:,:,:3][:,:,::-1].copy()

    def perform(self,w,action,allowed):
        if action.kind not in ('click','drag','right_click'): raise ValueError(action.kind)
        if action.kind=='drag': w.point(action.end)
        def ok(): return allowed() and self.active(w)
        if not ok(): return False
        sx,sy=w.point(action.start)
        self.xtest.fake_input(self.d,self.X.MotionNotify,x=sx,y=sy)
        self.d.sync()
        # Unity polls input on frames; let hover settle before pressing.
        time.sleep(.15)
        if not ok(): return False
        button=3 if action.kind=='right_click' else 1
        try:
            self.xtest.fake_input(self.d,self.X.ButtonPress,button)
            self.d.sync()
            # An immediate press/release can disappear between low-FPS frames.
            time.sleep(.30)
            if action.kind=='drag':
                ex,ey=w.point(action.end)
                for i in range(1,13):
                    if not ok(): return False
                    self.xtest.fake_input(self.d,self.X.MotionNotify,x=round(sx+(ex-sx)*i/12),y=round(sy+(ey-sy)*i/12))
                    self.d.sync()
                    time.sleep(.04)
                time.sleep(.15)
            elif action.kind not in ('click','right_click'):
                raise ValueError(action.kind)
        finally:
            self.xtest.fake_input(self.d,self.X.ButtonRelease,button)
            self.d.sync()
            # Keep the release over its target until Unity observes it.
            time.sleep(.25)
        if ok():
            x,y=w.point((.93,.06))
            self.xtest.fake_input(self.d,self.X.MotionNotify,x=x,y=y)
            self.d.sync()
        return True

    def close_game(self,w,stop,allowed):
        # Capture a Linux pidfd so PID recycling cannot target another process.
        import signal
        fd=os.pidfd_open(w.pid)
        try:
            if Path(f'/proc/{w.pid}/exe').resolve()!=self.game_exe:
                raise RuntimeError('Game executable changed; refusing recovery')
            if not allowed(): return
            signal.pidfd_send_signal(fd,signal.SIGTERM)
            import select
            poll=select.poll(); poll.register(fd,select.POLLIN)
            for _ in range(100):
                if poll.poll(0): return
                if stop.wait(.1) or not allowed(): return
            if allowed(): signal.pidfd_send_signal(fd,signal.SIGKILL)
            if not poll.poll(3000): raise RuntimeError('Game did not exit')
        finally:
            os.close(fd)

    def close(self):
        self.capture.close()
        self.d.close()
