import unittest
from pathlib import Path
import numpy as np
from PIL import Image
from recovery import disconnected, login_required, RetryBudget, recovery_delay
from core import Planner, Phase
from vision import Detector, color_objects

class RecoveryTest(unittest.TestCase):
    def test_login_service_failure_backs_off(self):
        text='关闭无法通过暴雪战网服务进行登录。请等待几分钟再再次尝试。'
        self.assertTrue(disconnected(text));self.assertEqual(recovery_delay(text),180)
        self.assertEqual(recovery_delay('与服务器断开连接'),10)

    def test_only_clear_disconnects(self):
        self.assertTrue(disconnected('你的游戏与暴雪战网服务断开连接，请稍后重试。'))
        self.assertFalse(disconnected('正在战网中连接好友'))
        self.assertFalse(disconnected('战斗'))
    def test_idle_disconnect_routes_to_bounded_recovery(self):
        self.assertTrue(disconnected('重新连接当前处于离线状态距离你的上一次操作已经过了很长时间，游戏连接中断。重新连接取消'))
        self.assertFalse(disconnected('重新连接取消'))
        self.assertFalse(disconnected('好友当前处于离线状态'))

    def test_login_requires_human(self):
        self.assertTrue(login_required('请输入验证码'))
        self.assertTrue(login_required('登录已过期'))
        self.assertFalse(login_required('在线 进入游戏'))
    def test_retry_budget_expires(self):
        now=[0]
        b=RetryBudget(lambda:now[0])
        for _ in range(3):b.take()
        with self.assertRaises(RuntimeError):b.take()
        now[0]=1800
        b.take()
        self.assertEqual(len(b.attempts),1)
    def test_recorded_national_start_screen(self):
        base=Path(__file__).resolve().parent/'fixtures'
        obs=Detector().observe(np.array(Image.open(base/'start-screen-game.png').convert('RGB')))
        self.assertEqual(obs.phase,Phase.START_SCREEN)
        action=Planner().next(obs)
        self.assertAlmostEqual(action.start[1],.808,delta=.02)

    def test_recorded_mainmenu(self):
        d=Detector()
        base=Path(__file__).resolve().parent/'fixtures'
        obs=d.observe(np.array(Image.open(base/'mainmenu-game.png').convert('RGB')))
        self.assertEqual(obs.phase,Phase.MENU)
        action=Planner().next(obs)
        self.assertAlmostEqual(action.start[1],.376,delta=.02)
