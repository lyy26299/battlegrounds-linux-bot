import unittest,tempfile
from pathlib import Path
from datetime import datetime
from schedule_window import inside_window,window_key,validate_schedule,save_schedule,load_schedule,BEIJING
class CustomScheduleTests(unittest.TestCase):
 def at(self,h,m=0):return datetime(2026,10,26,h,m,tzinfo=BEIJING)
 def test_boundaries(self):
  s={'start':'09:30','end':'12:15','enabled':True}
  for h,m,result in [(9,29,False),(9,30,True),(12,14,True),(12,15,False)]:self.assertEqual(inside_window(self.at(h,m),s),result)
 def test_overnight_window_identity(self):
  s={'start':'23:00','end':'02:00','enabled':True}
  self.assertTrue(inside_window(self.at(1),s));self.assertFalse(inside_window(self.at(2),s))
  self.assertEqual(window_key(self.at(1),s),'2026-10-25:23:00:02:00')
 def test_disabled(self):self.assertFalse(inside_window(self.at(10),{'start':'01:00','end':'12:00','enabled':False}))
 def test_invalid(self):
  for start,end,enabled in [('24:00','12:00',True),('1:00','12:00',True),('12:00','12:00',True),('01:00','12:00','yes')]:
   with self.assertRaises(ValueError):validate_schedule(dict(start=start,end=end,enabled=enabled))
 def test_persist_and_fail_closed(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'schedule.json';s=dict(start='22:00',end='06:30',enabled=True)
   save_schedule(s,p);self.assertEqual(load_schedule(p),s);p.write_text('bad');self.assertFalse(load_schedule(p)['enabled'])
