import json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from experiments.shadow_observer import ShadowObserver
class ShadowTests(unittest.TestCase):
 def test_identity_age_permissions_and_symlinks(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'shadow.json';reader=ShadowObserver(p)
   good={'utc':'2026-01-01T00:00:00Z','pid':123,'session':'a'*32,'control_allowed':False}
   with patch('experiments.shadow_observer.time.time',return_value=1767225601):
    p.write_text(json.dumps(good));p.chmod(0o600);self.assertIsNotNone(reader.read(123));self.assertIsNone(reader.read(124))
    for delta in ({'utc':'2025-12-31T23:59:57Z'},{'utc':'2026-01-01T00:00:03Z'},{'control_allowed':True}):
     p.write_text(json.dumps({**good,**delta}));self.assertIsNone(reader.read(123))
    p.write_text(json.dumps(good));p.chmod(0o644);self.assertIsNone(reader.read(123))
    target=Path(d)/'real';p.rename(target);p.symlink_to(target);self.assertIsNone(reader.read(123))
