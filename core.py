"""Pure decision logic. No desktop access or network traffic."""
from dataclasses import dataclass, field
from enum import Enum


class Phase(str, Enum):
    UNKNOWN = 'unknown'
    LOADING = 'loading'
    LOBBY = 'lobby'
    MENU = 'menu'
    START_SCREEN = 'start_screen'
    DISCONNECTED = 'disconnected'
    QUEUE = 'queue'
    HERO = 'hero'
    CHOICE = 'choice'
    RECRUIT = 'recruit'
    COMBAT = 'combat'
    RESULT = 'result'


@dataclass(frozen=True)
class Action:
    kind: str
    start: tuple[float, float]
    end: tuple[float, float] | None = None
    reason: str = ''


@dataclass
class Observation:
    phase: Phase = Phase.UNKNOWN
    gold: int | None = None
    seconds: int | None = None
    shop: list[tuple[float, float]] = field(default_factory=list)
    hand: list[tuple[float, float]] = field(default_factory=list)
    board: list[tuple[float, float]] = field(default_factory=list)
    buttons: dict[str, tuple[float, float]] = field(default_factory=dict)
    signature: str = ''
    evidence: list[str] = field(default_factory=list)


class Planner:
    """One action per fresh observation; repeated failures cause a stop."""
    def __init__(self):
        self.last_phase = Phase.UNKNOWN
        self.last_action = None
        self.last_signature = None
        self.repeats = 0
        self.actions_this_turn = 0
        self.round = 0
        self.games = 0
        self.match_active = False
        self.blocked_hand = frozenset()
        self.last_play_state = None

    def record(self, obs: Observation):
        # Animations and one failed OCR frame are not a phase transition.
        # Preserve both action-failure counters and completed-game accounting.
        if obs.phase in (Phase.UNKNOWN, Phase.DISCONNECTED, Phase.LOADING):
            return None
        if obs.phase in (Phase.RECRUIT, Phase.COMBAT):
            self.match_active = True
        if obs.phase != self.last_phase:
            if obs.phase == Phase.RECRUIT:
                self.round += 1
                self.actions_this_turn = 0
                self.blocked_hand = frozenset()
                self.last_play_state = None
            if obs.phase == Phase.RESULT:
                self.games += 1
                self.match_active = False
            elif obs.phase == Phase.LOBBY and self.match_active:
                # Some clients finish the reward animation and return directly.
                self.games += 1
                self.match_active = False
            if obs.phase == Phase.HERO:
                self.round = 0
            self.repeats = 0
            self.last_action = None
            self.last_signature = None
            self.last_phase = obs.phase

    def next(self, obs: Observation) -> Action | None:
        self.record(obs)
        if obs.phase in (Phase.UNKNOWN, Phase.DISCONNECTED, Phase.LOADING):
            return None
        if obs.phase in (Phase.QUEUE, Phase.COMBAT):
            return None
        action = self._plan(obs)
        if action is None:
            return None
        key = (action.kind, action.start, action.end)
        def near(a,b):
            return a is None and b is None or (a is not None and b is not None and max(abs(x-y) for x,y in zip(a,b)) < .015)
        same = self.last_action is not None and action.kind == self.last_action[0] and near(action.start,self.last_action[1]) and near(action.end,self.last_action[2])
        play = action.reason == '将可用手牌拖入己方战场'
        play_state = (obs.gold,len(obs.hand),len(obs.board))
        unchanged = play_state == self.last_play_state if play else obs.signature == self.last_signature
        if same and unchanged:
            self.repeats += 1
            if self.repeats >= 3:
                if play:
                    # A targeted or otherwise unplayable card must not block the whole hand.
                    index=min(range(len(obs.hand)),key=lambda i:sum((a-b)**2 for a,b in zip(obs.hand[i],action.start)))
                    self.blocked_hand=self.blocked_hand|{index}
                    self.last_action=None;self.last_play_state=None;self.repeats=0
                    return None
                raise RuntimeError('同一操作连续无效，已停止。请检查截图和窗口。')
        else:
            self.repeats = 0
        self.last_action = key
        self.last_play_state = play_state if play else None
        self.last_signature = obs.signature
        if obs.phase == Phase.RECRUIT:
            self.actions_this_turn += 1
        return action

    def _plan(self, obs):
        if obs.phase == Phase.START_SCREEN and "enter" in obs.buttons:
            return Action("click", obs.buttons["enter"], reason="进入国服游戏主菜单")
        if obs.phase == Phase.MENU and "battlegrounds" in obs.buttons:
            return Action("click", obs.buttons["battlegrounds"], reason="从主菜单进入酒馆战棋")
        if obs.phase == Phase.LOBBY and 'start' in obs.buttons:
            return Action('click', obs.buttons['start'], reason='开始下一局')
        if obs.phase == Phase.RESULT and 'continue' in obs.buttons:
            return Action('click', obs.buttons['continue'], reason='关闭结算')
        if obs.phase == Phase.HERO:
            if 'confirm_active' in obs.buttons:
                return Action('click', obs.buttons['confirm_active'], reason='确认免费英雄')
            return Action('click', (0.39, 0.46), reason='选择中间的免费英雄；不使用重掷')
        if obs.phase == Phase.CHOICE:
            if 'dismiss_match_error' in obs.buttons:
                return Action('click',obs.buttons['dismiss_match_error'],reason='关闭对手连接失败提示')
            if 'dismiss_weekly' in obs.buttons:
                return Action('click',obs.buttons['dismiss_weekly'],reason='关闭任务提示')
            if 'confirm_choice' in obs.buttons:
                return Action('click', obs.buttons['confirm_choice'], reason='确认对局内选项')
            if 'choice' in obs.buttons:
                return Action('click', obs.buttons['choice'], reason='选择对局内选项')
        if obs.phase != Phase.RECRUIT:
            return None
        if obs.seconds is None or obs.seconds < 5 or self.actions_this_turn >= 36:
            return None
        if 'cancel_target' in obs.buttons:
            return Action('right_click',obs.buttons['cancel_target'],reason='取消法术目标选择')
        # Resolve the hand before spending more gold. Never buy paid rerolls,
        # passes, or anything outside a verified recruit phase.
        playable_hand=[point for index,point in enumerate(obs.hand) if index not in self.blocked_hand]
        if playable_hand:
            if len(obs.board) >= 7:
                return Action('drag', obs.board[0], (0.50, 0.18), '满场时出售最左随从')
            target=obs.board[0] if obs.board else (0.50,0.57)
            return Action('drag', playable_hand[0], target, '将可用手牌拖入己方战场')
        if obs.gold is not None and obs.gold >= 3 and obs.shop and len(obs.hand)<10:
            return Action('drag', obs.shop[0], (0.50, 0.90), '购买最左可识别随从')
        return None
