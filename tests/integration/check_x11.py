"""Real Xvfb/Openbox integration, synthetic window only, no game or account."""
import os, sys, time, subprocess, json, threading
from pathlib import Path

if '--window' in sys.argv:
    from Xlib import X, Xatom, display
    d = display.Display()
    w = d.screen().root.create_window(20, 40, 1024, 768, 0,
        d.screen().root_depth, X.InputOutput, X.CopyFromParent,
        background_pixel=0xCC2244, event_mask=X.ButtonPressMask|X.ButtonReleaseMask)
    title = sys.argv[-1]
    w.set_wm_name(title)
    w.change_property(d.intern_atom('_NET_WM_NAME'), d.intern_atom('UTF8_STRING'), 8, title.encode())
    w.change_property(d.intern_atom('_NET_WM_PID'), Xatom.CARDINAL, 32, [os.getpid()])
    w.map(); d.sync()
    while True:
        e = d.next_event()
        if e.type in (X.ButtonPress, X.ButtonRelease):
            print(json.dumps([e.type, e.event_x, e.event_y]), flush=True)

sys.path.insert(0, '/app')
from linux_backend import Desktop
from core import Action

def wait_for(f):
    deadline=time.monotonic()+10
    while time.monotonic()<deadline:
        value=f()
        if value:return value
        time.sleep(.1)
    raise AssertionError('Timed out: '+str(f))

game=subprocess.Popen([sys.executable,__file__,'--window','Hearthstone'],stdout=subprocess.PIPE,text=True)
events=[]
threading.Thread(target=lambda: events.extend(game.stdout),daemon=True).start()
d=None; other=None
results=[]
try:
    d=Desktop(sys.executable)
    w=wait_for(d.find)
    wait_for(lambda:d.active(w))
    frame=d.image(w)
    assert frame.shape==(768,1024,3),frame.shape
    assert list(frame[384,512])==[204,34,68],frame[384,512]
    results.append('window identity, geometry and RGB screenshot')
    assert d.perform(w,Action('click',(.5,.5)),lambda:True)
    wait_for(lambda:len(events)>=2)
    assert [json.loads(e) for e in events[:2]]==[[4,512,384],[5,512,384]],events
    results.append('XTest click reaches client coordinates')
    assert d.perform(w,Action('drag',(.3,.4),(.7,.6)),lambda:True)
    wait_for(lambda:len(events)>=4)
    assert [json.loads(e) for e in events[2:4]]==[[4,307,307],[5,717,461]],events
    results.append('XTest drag reaches expected endpoint')
    assert not d.perform(w,Action('click',(.5,.5)),lambda:False)
    time.sleep(.1); assert len(events)==4
    results.append('paused controller emits no clicks')
    other=subprocess.Popen([sys.executable,__file__,'--window','Other application'],stdout=subprocess.DEVNULL)
    wait_for(lambda:not d.active(w))
    assert not d.perform(w,Action('click',(.5,.5)),lambda:True)
    time.sleep(.1); assert len(events)==4
    results.append('foreign focused window blocks input')
    d.close_game(w,threading.Event(),lambda:True)
    game.wait(timeout=3)
    assert other.poll() is None
    assert d.find() is None
    results.append('pidfd recovery closes only matching process')
    print(json.dumps({'status':'passed','platform':os.uname().machine,'checks':results,'real_game':False},indent=2))
finally:
    if d:d.close()
    for child in (game,other):
        if child and child.poll() is None:child.terminate();child.wait(timeout=3)
