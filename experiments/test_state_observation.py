import copy,unittest
from experiments.state_observation import observation
class ObservationTests(unittest.TestCase):
 def state(self):return dict(available=True,busy=False,game_over=False,combat_tag=0,options_id=12,game_id='game',session='boot',pid=9,turn=3,updates=50,seconds_candidate=15.4,gold_candidate=3,entities=[],shop_candidates=[dict(entity=20,position=1,x=.3,y=.4,input_ready=True)])
 def pair(self):
  a=self.state();b=copy.deepcopy(a);b['updates']+=5;return a,b
 def test_ready_pair_produces_normalized_cards(self):
  a,b=self.pair();o=observation(a,b);self.assertEqual(o.gold,3);self.assertEqual(o.shop,[(.3,.4)])
 def test_mismatched_or_unready_context_never_controls(self):
  for update in ({'session':'new'},{'options_id':13},{'busy':True},{'game_over':True},{'combat_tag':1},{'seconds_candidate':2},{'updates':50}):
   a,b=self.pair();b.update(update);self.assertIsNone(observation(a,b))
 def test_duplicate_or_offscreen_cards_never_control(self):
  for update in ({'x':float('nan')},{'x':2},{'input_ready':False}):
   a,b=self.pair();b['shop_candidates'][0].update(update);self.assertIsNone(observation(a,b))
  a,b=self.pair();b['shop_candidates']*=2;self.assertIsNone(observation(a,b))
 def test_spell_in_hand_stays_on_verified_fallback(self):
  a,b=self.pair();b['entities']=[dict(entity=9,zone=3,card_type=5,position=1)];self.assertIsNone(observation(a,b))

 def test_animation_with_unchanged_options_is_rejected(self):
  a,b=self.pair();b['shop_candidates'][0]['x']+=.1;self.assertIsNone(observation(a,b))
 def test_changed_shop_identity_is_rejected(self):
  a,b=self.pair();b['shop_candidates'][0]['entity']=21;self.assertIsNone(observation(a,b))
 def test_resource_change_is_rejected(self):
  a,b=self.pair();b['gold_candidate']=2;self.assertIsNone(observation(a,b))
