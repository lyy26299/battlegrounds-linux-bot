import unittest
from state_reader import available_gold
class GoldTests(unittest.TestCase):
 def test_pending_spend_and_temp_spend_deducted(self):
  self.assertEqual(available_gold(10,3,2,3,1),5)
 def test_unknown_is_not_zero(self):
  self.assertIsNone(available_gold(None,3,0,0,0))
 def test_game_getter_clamps_negative(self):
  self.assertEqual(available_gold(3,3,0,3,0),0)
if __name__=='__main__':unittest.main()
