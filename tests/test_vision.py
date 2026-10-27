import unittest
from pathlib import Path
import numpy as np
from PIL import Image
from core import Phase
from vision import Detector, parse_gold

class VisionReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.detector=Detector()
        cls.samples=Path(__file__).resolve().parent/'fixtures'
    def read(self,name):
        return self.detector.observe(np.array(Image.open(self.samples/(name+'-game.png')).convert('RGB')))
    def test_real_result_and_lobby(self):
        self.assertEqual(self.read('result').phase,Phase.RESULT)
        self.assertEqual(self.read('lobby').phase,Phase.LOBBY)
    def test_hero_does_not_confirm_before_selection(self):
        obs=self.read('hero')
        self.assertEqual(obs.phase,Phase.HERO)
        self.assertNotIn('confirm_active',obs.buttons)
    def test_one_card_in_hand(self):
        obs=self.read('hand')
        self.assertEqual(obs.phase,Phase.RECRUIT)
        self.assertEqual(obs.gold,7)
        self.assertEqual(len(obs.hand),1)
        self.assertEqual(len(obs.shop),3)
        self.assertEqual(len(obs.board),0)
    def test_split_outline_is_one_minion(self):
        obs=self.read('board-one')
        self.assertEqual(len(obs.board),1)
        self.assertEqual(len(obs.hand),0)
    def test_recruit_does_not_require_bob_hover_name(self):
        obs=self.read("recruit-no-hover")
        self.assertEqual(obs.phase,Phase.RECRUIT)
        self.assertEqual(obs.gold,0)
        self.assertEqual(len(obs.hand),1)

    def test_current_trinket_screens(self):
        o=self.read("trinket")
        self.assertEqual(o.phase,Phase.CHOICE)
        self.assertNotIn("confirm_choice",o.buttons)
        self.assertIn("confirm_choice",self.read("trinket-selected").buttons)

    def test_gold_constraints(self):
        for text,want in [('7/7',7),('77',7),('710',7),('1010',10),('7.7',7),('18/10',18),('7/6',7),('76',7),('1/0',None),('30',None),('金币',None)]:
            with self.subTest(text=text):self.assertEqual(parse_gold(text),want)
    def test_black_frame_never_clicks(self):
        obs=self.detector.observe(np.zeros((768,1024,3),dtype=np.uint8))
        self.assertEqual(obs.phase,Phase.UNKNOWN)
        self.assertFalse(obs.buttons)

    def test_cloud_trinket_preserves_deadline(self):
        obs=self.read('trinket-cloud')
        self.assertEqual(obs.phase,Phase.CHOICE)
        self.assertIsNotNone(obs.seconds)
        self.assertGreater(obs.seconds,0)
        self.assertLessEqual(obs.seconds,17)
        self.assertNotIn('confirm_choice',obs.buttons)

    def test_cloud_result_with_exclamation_mark(self):
        obs=self.read('result-cloud')
        self.assertEqual(obs.phase,Phase.RESULT)
        self.assertIn('continue',obs.buttons)

    def test_cloud_startup_waits_without_clicks(self):
        obs=self.read('loading-cloud')
        self.assertEqual(obs.phase,Phase.LOADING)
        self.assertFalse(obs.buttons)
        from core import Planner
        self.assertIsNone(Planner().next(obs))

    def test_cloud_three_card_choice_with_split_edges(self):
        obs=self.read('hero-choice-cloud')
        self.assertEqual(obs.phase,Phase.CHOICE)
        self.assertIn('choice',obs.buttons)
        x,y=obs.buttons['choice']
        self.assertTrue(.15<x<.28 and .3<y<.5)
        from vision import three_choice_cards
        self.assertEqual(three_choice_cards(np.zeros((768,1024,3),dtype=np.uint8)),[])

    def test_targeted_spell_cancel_and_minion_badges(self):
        from core import Planner
        obs=self.read('targeting-cloud')
        self.assertEqual(obs.phase,Phase.RECRUIT)
        self.assertIn('cancel_target',obs.buttons)
        self.assertEqual(len(obs.hand),2)
        self.assertEqual(Planner().next(obs).kind,'right_click')
        from vision import targeting_arrow
        for name in ('hand','board-one','recruit-no-hover','hero-choice-cloud'):
            im=np.array(Image.open(self.samples/(name+'-game.png')).convert('RGB'))
            self.assertFalse(targeting_arrow(im),name)

    def test_scaled_800x600_critical_screens(self):
        for name,phase in [('lobby',Phase.LOBBY),('hand',Phase.RECRUIT),('hero-choice-cloud',Phase.CHOICE),('targeting-cloud',Phase.RECRUIT)]:
            im=Image.open(self.samples/(name+'-game.png')).convert('RGB').resize((800,600),Image.Resampling.LANCZOS)
            obs=self.detector.observe(np.array(im))
            self.assertEqual(obs.phase,phase,name)
            if name=='hand':self.assertEqual(len(obs.hand),1)
            if name=='targeting-cloud':self.assertIn('cancel_target',obs.buttons)
            if name=='hero-choice-cloud':self.assertIn('choice',obs.buttons)

    def test_alliance_choice_blocks_hand_dragging(self):
        from core import Planner
        obs=self.read('alliance-choice')
        self.assertEqual(obs.phase,Phase.CHOICE)
        self.assertEqual(obs.seconds,35)
        self.assertEqual(obs.hand,[])
        action=Planner().next(obs)
        self.assertEqual(action.kind,'click')
        self.assertTrue(.28<action.start[0]<.45 and .3<action.start[1]<.6)

    def test_choice_modal_with_connected_green_edges(self):
        from core import Planner
        obs=self.read('choice-hidden-modal')
        self.assertEqual(obs.phase,Phase.CHOICE)
        self.assertEqual(obs.shop,[])
        action=Planner().next(obs)
        self.assertEqual(action.kind,'click')
        self.assertTrue(.18<action.start[0]<.30 and .3<action.start[1]<.6)

    def test_opponent_connection_dialog_precedes_lobby(self):
        from core import Planner
        obs=self.read('opponent-connect-error')
        self.assertEqual(obs.phase,Phase.CHOICE)
        self.assertNotIn('start',obs.buttons)
        action=Planner().next(obs)
        self.assertEqual(action.reason,'关闭对手连接失败提示')
        self.assertTrue(.45<action.start[0]<.55 and .55<action.start[1]<.65)
