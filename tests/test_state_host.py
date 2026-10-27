import json,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from state_host import FileObserver
from install_services import units

class HostStateTests(unittest.TestCase):
    def test_freshness_boot_and_pid_identity(self):
        with tempfile.TemporaryDirectory() as d:
            observer=FileObserver.__new__(FileObserver);observer.path=Path(d)/'state.json';observer.boot='boot'
            good={'pid':10,'start_ticks':123,'boot_id':'boot','monotonic':100,'state':{'available':True,'m_mode':15}}
            with patch('state_host.identity',return_value=123),patch('state_host.time.monotonic',return_value=101):
                observer.path.write_text(json.dumps(good));self.assertTrue(observer.observe(10)['available'])
                for update in ({'pid':11},{'start_ticks':124},{'boot_id':'old'},{'monotonic':95},{'monotonic':102}):
                    observer.path.write_text(json.dumps({**good,**update}));self.assertFalse(observer.observe(10)['available'])
    def test_missing_or_corrupt_snapshot_falls_back(self):
        with tempfile.TemporaryDirectory() as d:
            o=FileObserver.__new__(FileObserver);o.path=Path(d)/'x';o.boot='boot'
            self.assertFalse(o.observe(10)['available'])
            o.path.write_text('{broken');self.assertFalse(o.observe(10)['available'])
    def test_game_host_does_not_auto_restart_past_retry_budget(self):
        u=units(Path('/tmp/bot'))
        self.assertIn('Restart=no',u['bg-game.service'])
        self.assertIn('KillMode=control-group',u['bg-game.service'])
        self.assertIn('--state-host',u['bg-bot.service'])
        self.assertIn('KillMode=process',u['bg-bot.service'])
