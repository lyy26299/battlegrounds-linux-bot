import hashlib,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from experiments.loader_environment import game_environment
class LoaderTests(unittest.TestCase):
 def fixture(self,d):
  root=Path(d);exe=root/'Hearthstone.x86_64';exe.write_bytes(b'exe')
  assembly=root/'Hearthstone_Data/Managed/Assembly-CSharp.dll';assembly.parent.mkdir(parents=True);assembly.write_bytes(b'game')
  core=root/'BepInEx';core.mkdir();lib=root/'libdoorstop.so';lib.write_bytes(b'loader')
  (core/'shadow-install-manifest.json').write_text(json.dumps({'files':{'libdoorstop.so':hashlib.sha256(b'loader').hexdigest()}}))
  return exe,hashlib.sha256(b'game').hexdigest()
 def test_changed_game_refuses_loader(self):
  with tempfile.TemporaryDirectory() as d:
   exe,_=self.fixture(d)
   with self.assertRaises(RuntimeError):game_environment(exe,{})
 def test_child_environment_and_debug_disabled(self):
  with tempfile.TemporaryDirectory() as d:
   exe,h=self.fixture(d);base={'PATH':'keep'}
   with patch('experiments.loader_environment.ASSEMBLY_SHA',h):env=game_environment(exe,base)
   self.assertEqual(base,{'PATH':'keep'});self.assertEqual(env['DOORSTOP_MONO_DEBUG_ENABLED'],'0');self.assertEqual(env['DOORSTOP_MONO_DEBUG_SUSPEND'],'0')
 def test_changed_loader_and_unknown_preload_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   exe,h=self.fixture(d)
   with patch('experiments.loader_environment.ASSEMBLY_SHA',h):
    with self.assertRaises(RuntimeError):game_environment(exe,{'LD_PRELOAD':'other.so'})
    (Path(d)/'libdoorstop.so').write_bytes(b'changed')
    with self.assertRaises(RuntimeError):game_environment(exe,{})
