import unittest
from core import Action, Observation, Phase, Planner


class WorkflowTests(unittest.TestCase):
    def test_full_cycle(self):
        p = Planner()
        self.assertEqual(p.next(Observation(Phase.LOBBY, buttons={'start': (.84,.8)})).kind, 'click')
        self.assertIsNone(p.next(Observation(Phase.QUEUE)))
        self.assertIn('免费英雄', p.next(Observation(Phase.HERO)).reason)
        self.assertEqual(p.next(Observation(Phase.HERO, buttons={'confirm_active': (.5,.79)}, signature='selected')).start, (.5,.79))
        buy = p.next(Observation(Phase.RECRUIT, gold=3, seconds=30, shop=[(.35,.37)], signature='before'))
        self.assertEqual(buy.end, (.5,.9))
        play = p.next(Observation(Phase.RECRUIT, gold=0, seconds=25, hand=[(.48,.94)], signature='after'))
        self.assertEqual(play.end, (.5,.57))
        self.assertIsNone(p.next(Observation(Phase.COMBAT)))
        self.assertEqual(p.next(Observation(Phase.RESULT, buttons={'continue': (.5,.5)})).kind, 'click')
        self.assertEqual(p.games, 1)
        self.assertEqual(p.next(Observation(Phase.LOBBY, buttons={'start': (.84,.8)})).reason, '开始下一局')

    def test_unknown_gold_and_phase_never_spend(self):
        p = Planner()
        for phase in [Phase.UNKNOWN, Phase.QUEUE, Phase.COMBAT]:
            self.assertIsNone(p.next(Observation(phase, gold=10, seconds=30, shop=[(.3,.3)])))
        self.assertIsNone(p.next(Observation(Phase.RECRUIT, seconds=30, shop=[(.3,.3)])))

    def test_late_turn_no_action(self):
        self.assertIsNone(Planner().next(Observation(Phase.RECRUIT,gold=10,seconds=2,shop=[(.3,.3)])))

    def test_full_board_sell_before_play(self):
        a = Planner().next(Observation(Phase.RECRUIT,seconds=30,hand=[(.5,.9)],board=[(.2+i*.08,.57) for i in range(7)]))
        self.assertEqual(a.end, (.5,.18))

    def test_failure_stops(self):
        p = Planner()
        o = Observation(Phase.RECRUIT,gold=3,seconds=30,shop=[(.3,.3)],signature='unchanged')
        for _ in range(3):
            p.next(o)
        with self.assertRaises(RuntimeError):
            p.next(o)

    def test_unknown_animation_does_not_count_result_twice(self):
        p = Planner()
        p.next(Observation(Phase.RESULT))
        p.next(Observation(Phase.UNKNOWN))
        p.next(Observation(Phase.RESULT))
        self.assertEqual(p.games, 1)

    def test_unknown_frame_does_not_clear_failure_limit(self):
        p = Planner()
        o = Observation(Phase.RECRUIT,gold=3,seconds=30,shop=[(.3,.3)],signature='unchanged')
        for _ in range(3):
            p.next(o)
            p.next(Observation(Phase.UNKNOWN))
        self.assertEqual(p.round, 1)
        self.assertEqual(p.actions_this_turn, 3)
        with self.assertRaises(RuntimeError):
            p.next(o)


if __name__ == '__main__':
    unittest.main()

class CoordinateJitterTests(unittest.TestCase):
    def test_ocr_jitter_does_not_reset_failed_click_limit(self):
        planner = Planner()
        for y in (.3756, .3769, .3756):
            planner.next(Observation(phase=Phase.MENU,buttons={'battlegrounds':(.5,y)},signature='unchanged'))
        with self.assertRaises(RuntimeError):
            planner.next(Observation(phase=Phase.MENU,buttons={'battlegrounds':(.5,.3769)},signature='unchanged'))

class DirectLobbyCompletionTests(unittest.TestCase):
    def test_match_returning_directly_to_lobby_counts_before_queue(self):
        p=Planner()
        p.record(Observation(Phase.RECRUIT))
        p.record(Observation(Phase.COMBAT))
        p.record(Observation(Phase.UNKNOWN))
        p.record(Observation(Phase.LOBBY,buttons={'start':(.84,.8)}))
        self.assertEqual(p.games,1)
        self.assertIsNone(p.last_action)
        p.record(Observation(Phase.LOBBY))
        self.assertEqual(p.games,1)
    def test_result_then_lobby_is_one_game(self):
        p=Planner()
        for phase in (Phase.RECRUIT,Phase.COMBAT,Phase.RESULT,Phase.UNKNOWN,Phase.LOBBY):
            p.record(Observation(phase))
        self.assertEqual(p.games,1)
    def test_initial_lobby_and_queue_do_not_count(self):
        p=Planner()
        for phase in (Phase.LOBBY,Phase.QUEUE,Phase.UNKNOWN,Phase.LOBBY):
            p.record(Observation(phase))
        self.assertEqual(p.games,0)
    def test_recovery_reset_does_not_count_aborted_match(self):
        p=Planner();p.record(Observation(Phase.RECRUIT))
        restarted=Planner();restarted.games=p.games
        restarted.record(Observation(Phase.LOBBY))
        self.assertEqual(restarted.games,0)

class UnplayableHandTests(unittest.TestCase):
    def test_unplayable_first_card_does_not_block_second_card(self):
        p=Planner()
        o=Observation(Phase.RECRUIT,gold=3,seconds=30,hand=[(.43,.93),(.52,.93)],shop=[(.3,.3)],signature='hand')
        for _ in range(3):self.assertEqual(p.next(o).start,(.43,.93))
        self.assertIsNone(p.next(o))
        self.assertEqual(p.next(o).start,(.52,.93))
    def test_one_blocked_card_can_buy_minion_but_full_hand_cannot(self):
        p=Planner();o=Observation(Phase.RECRUIT,gold=3,seconds=30,hand=[(.43,.93)],shop=[(.3,.3)])
        for _ in range(4):p.next(o)
        self.assertEqual(p.next(o).reason,'购买最左可识别随从')
        p.record(Observation(Phase.COMBAT));p.record(Observation(Phase.RECRUIT))
        self.assertEqual(p.blocked_hand,frozenset())
    def test_jittering_visual_signature_does_not_repeat_spell_forever(self):
        p=Planner()
        for i in range(3):p.next(Observation(Phase.RECRUIT,gold=3,seconds=30,hand=[(.43,.93)],signature=str(i)))
        self.assertIsNone(p.next(Observation(Phase.RECRUIT,gold=3,seconds=25,hand=[(.43,.93)],signature='another')))
