import unittest
from supervisor import recovery_loop
class SupervisorTests(unittest.TestCase):
 def simulate(self,results,stop_during_wait=False):
  active=[True];delays=[];closed=[];reports=[];calls=[]
  def launch():calls.append(1);return results.pop(0)
  def wait(delay):
   delays.append(delay)
   if stop_during_wait:active[0]=False
  code=recovery_loop(launch,lambda:active[0],wait,lambda:closed.append(1),lambda status,**kw:reports.append(status))
  return code,delays,closed,reports,len(calls)
 def fault(self):return 1,{'error':'RuntimeError: 同一操作连续无效','elapsed_seconds':60}
 def test_stall_restarts_then_normal_exit_stays_stopped(self):
  r=self.simulate([self.fault(),(0,{})]);self.assertEqual((r[0],r[1],r[4]),(0,[30],2))
 def test_backoff_and_long_cooldown(self):
  r=self.simulate([self.fault() for _ in range(4)]+[(0,{})]);self.assertEqual(r[1],[30,120,300,1800])
 def test_manual_stop_or_schedule_end_during_wait_never_relaunches(self):
  r=self.simulate([self.fault()],True);self.assertEqual(r[4],1);self.assertEqual(r[0],0)
 def test_login_errors_need_human(self):
  r=self.simulate([(1,{'error':'Login or verification required; complete it manually'})]);self.assertEqual(r[0],1);self.assertEqual(r[1],[])
 def test_unknown_screen_recovers(self):
  r=self.simulate([(1,{'error':'Unrecognized screen for two minutes'}),(0,{})]);self.assertEqual(r[1],[30])
 def test_no_permission_never_launches(self):
  self.assertEqual(recovery_loop(lambda:self.fail(),lambda:False,lambda _:self.fail(),lambda:self.fail(),lambda *a,**kw:self.fail()),0)
