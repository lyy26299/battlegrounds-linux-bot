import tempfile
import unittest
from pathlib import Path
from core import Phase,Action
from control import Lock,stale,interval
from linux_backend import Window,validate_window
from low_spec import update
from install_services import units

class LinuxLogicTests(unittest.TestCase):
    def test_no_click_after_slow_recognition(self):
        self.assertTrue(stale(8,5))
        self.assertFalse(stale(8,3))
        self.assertFalse(stale(None,20))
    def test_ocr_pacing(self):
        self.assertEqual(interval(Phase.COMBAT),4)
        self.assertEqual(interval(Phase.RECRUIT),.6)
        self.assertEqual(interval(Phase.HERO,Action('click',(.5,.5))),3)
    def test_display_geometry(self):
        w=Window(1,2,10,20,1024,768)
        validate_window(w,1280,960)
        self.assertEqual(w.point((.5,.5)),(522,404))
        for bad in (Window(1,2,-1,0,1024,768),Window(1,2,0,0,1280,720),Window(1,2,300,0,1024,768)):
            with self.assertRaises(RuntimeError):validate_window(bad,1280,960)
        with self.assertRaises(ValueError):w.point((0,.5))
    def test_duplicate_controller_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'lock'
            with Lock(p):
                with self.assertRaises(RuntimeError):
                    with Lock(p):pass
            with Lock(p):pass
    def test_low_spec_preserves_other_settings(self):
        result=update('sound=0.4\ntargetframerate=144\nfoo=bar\ntargetframerate=120\n',30)
        self.assertEqual(result.count('targetframerate='),1)
        self.assertIn('targetframerate=30',result)
        self.assertIn('sound=0.4',result)
        self.assertIn('foo=bar',result)
        self.assertEqual(update(result,30),result)
    def test_resolution_update_and_preservation(self):
        source='graphicswidth=1024\ngraphicsheight=768\nsound=0.5\n'
        changed=update(source,20,'800x600')
        self.assertIn('graphicswidth=800',changed)
        self.assertIn('graphicsheight=600',changed)
        self.assertIn('sound=0.5',changed)
        self.assertEqual(dict(line.split('=',1) for line in update(changed,20).splitlines()),
                         dict(line.split('=',1) for line in changed.splitlines()))
        with self.assertRaises(ValueError):update(source,20,'640x480')
    def test_unity_resolution_preserves_unrelated_preferences(self):
        from low_spec import unity_resolution
        import xml.etree.ElementTree as ET
        source='<unity_prefs><pref name="Screenmanager Resolution Width" type="int">1024</pref><pref name="Screenmanager Resolution Height" type="int">768</pref><pref name="Screenmanager Resolution Use Native" type="int">1</pref><pref name="other" type="string">unchanged</pref></unity_prefs>'
        result={n.attrib['name']:n.text for n in ET.fromstring(unity_resolution(source,'800x600'))}
        self.assertEqual(result['Screenmanager Resolution Width'],'800')
        self.assertEqual(result['Screenmanager Resolution Height'],'600')
        self.assertEqual(result['Screenmanager Resolution Use Native'],'0')
        self.assertEqual(result['other'],'unchanged')
        with self.assertRaises(ValueError):unity_resolution('<unity_prefs/>','800x600')
    def test_timer_and_stop_behavior(self):
        u=units(Path('/tmp/example with spaces'))
        self.assertIn('Asia/Shanghai',u['bg-bot.timer'])
        self.assertIn('OnFailure=bg-attention.service',u['bg-bot.service'])
        self.assertIn('/usr/bin/xmessage',u['bg-attention.service'])
        self.assertIn('Restart=no',u['bg-attention.service'])
        self.assertIn('Persistent=true',u['bg-bot.timer'])
        self.assertIn('--daily-window',u['bg-bot.service'])
        self.assertIn('Restart=no',u['bg-bot.service'])
        self.assertIn('TimeoutStopSec=45',u['bg-bot.service'])
        self.assertIn('stop_game.py',u['bg-game.service'])
        self.assertIn('ExecStopPost=/usr/bin/systemctl --user stop bg-game.service',u['bg-bot.service'])
        self.assertIn('KillMode=process',u['bg-bot.service'])
        self.assertIn('Type=notify',u['bg-desktop.service'])
        self.assertIn('"/tmp/example with spaces/.venv/bin/python"',u['bg-bot.service'])

class InputInterlockTests(unittest.TestCase):
    def desktop(self):
        from linux_backend import Desktop
        from types import SimpleNamespace
        d=Desktop.__new__(Desktop)
        d.X=SimpleNamespace(MotionNotify=1,ButtonPress=2,ButtonRelease=3)
        self.events=[]
        d.xtest=SimpleNamespace(fake_input=lambda *args,**kw:self.events.append((args[1],kw)))
        d.d=SimpleNamespace(sync=lambda:None)
        d.active=lambda w:True
        return d
    def test_no_input_when_paused_or_past_noon(self):
        d=self.desktop()
        self.assertFalse(d.perform(Window(1,2,0,0,1024,768),Action('click',(.5,.5)),lambda:False))
        self.assertFalse(self.events)
    def test_no_input_when_focus_changed(self):
        d=self.desktop(); d.active=lambda w:False
        self.assertFalse(d.perform(Window(1,2,0,0,1024,768),Action('click',(.5,.5)),lambda:True))
        self.assertFalse(self.events)
    def test_drag_releases_button_when_stopped(self):
        d=self.desktop(); calls=[0]
        def allowed():
            calls[0]+=1
            return calls[0]<3
        result=d.perform(Window(1,2,0,0,1024,768),Action('drag',(.5,.5),(.5,.7)),allowed)
        self.assertFalse(result)
        self.assertEqual([e[0] for e in self.events],[1,2,3])

class TransitionObservationTests(unittest.TestCase):
    def test_only_verified_loading_can_skip_and_never_beyond_five_seconds(self):
        from control import defer_transition_ocr
        state={'available':True,'scene_present':True,'m_sceneLoaded':True,'m_transitioning':True}
        self.assertTrue(defer_transition_ocr(state,2))
        for elapsed in (-1,5,10):self.assertFalse(defer_transition_ocr(state,elapsed))
        for change in ({'available':False},{'scene_present':False},{'m_transitioning':False}):
            self.assertFalse(defer_transition_ocr({**state,**change},2))
        self.assertFalse(defer_transition_ocr(None,2))


class OwnedShutdownTests(unittest.TestCase):
    def test_shutdown_requires_exact_executable_and_service(self):
        from stop_game import owned
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); p=root/'123';p.mkdir()
            exe=root/'game';exe.touch();(p/'exe').symlink_to(exe)
            cgroup=p/'cgroup'
            cgroup.write_text('0::/user.slice/app.slice/bg-game.service\n')
            self.assertTrue(owned(123,exe.resolve(),root))
            self.assertFalse(owned(123,root/'another',root))
            cgroup.write_text('0::/user.slice/app.slice/manual-game.service\n')
            self.assertFalse(owned(123,exe.resolve(),root))
