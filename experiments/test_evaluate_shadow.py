"""Prevent action duration from being misreported as reader disagreement."""
import json,subprocess,sys,tempfile,unittest
from pathlib import Path
class TimingTests(unittest.TestCase):
 def evaluate(self,event):
  snapshot=dict(utc='2026-10-25T14:00:00+00:00',session='test',updates=1,rendered_frames=1,render_interval=1,available=True,busy=False,combat_tag=0,gold_candidate=3,turn=1,control_allowed=False)
  with tempfile.TemporaryDirectory() as folder:
   a=Path(folder)/'shadow';b=Path(folder)/'events'
   a.write_text(json.dumps(snapshot)+'\n');b.write_text(json.dumps(event)+'\n')
   return json.loads(subprocess.check_output([sys.executable,str(Path(__file__).with_name('evaluate_shadow.py')),str(a),str(b)],text=True))
 def event(self):return dict(time='2026-10-25T14:00:05+00:00',recognition_seconds=2,action={'kind':'drag'},observation={'phase':'recruit','gold':3})
 def test_exact_capture_wins_over_post_action_timestamp(self):
  e=self.event();e['capture_utc']='2026-10-25T14:00:00+00:00';r=self.evaluate(e);self.assertEqual(r['gold_matches'],1)
 def test_old_actions_have_no_reliable_capture_time(self):
  r=self.evaluate(self.event());self.assertEqual(r['gold_checks'],0);self.assertEqual(r['skipped_ambiguous_capture_time'],1)
