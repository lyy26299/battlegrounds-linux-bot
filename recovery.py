"""Bounded recovery through the existing official Battle.net launcher.
No credentials, memory inspection, network filtering, or anti-cheat changes.
"""
from collections import deque
from pathlib import Path
import time


def login_service_unavailable(text):
    return '无法通过' in text and '战网' in text and '登录' in text and '几分钟' in text

def recovery_delay(text):
    return 180 if login_service_unavailable(text) else 10

def disconnected(text):
    if login_service_unavailable(text):return True
    # National client idle-disconnect dialog observed after waking Wuying.
    # Both phrases are required to avoid treating ordinary reconnect labels as faults.
    if '当前处于离线状态' in text and '游戏连接中断' in text:
        return True
    return any(s in text for s in ('与暴雪战网服务断开连接', '与战网服务断开连接',
        '与服务器断开连接', '与游戏服务器断开连接', '无法连接到暴雪游戏服务器'))


def login_required(text):
    return any(s in text for s in ('验证码', '身份验证器', '扫码登录', '账号密码登录', '输入密码', '登录已过期'))


class RetryBudget:
    def __init__(self, clock=time.monotonic):
        self.clock=clock
        self.attempts=deque()

    def take(self):
        now=self.clock()
        while self.attempts and now-self.attempts[0]>=1800:
            self.attempts.popleft()
        if len(self.attempts)>=3:
            raise RuntimeError('30分钟内已尝试恢复3次，停止并等待人工检查。')
        self.attempts.append(now)
