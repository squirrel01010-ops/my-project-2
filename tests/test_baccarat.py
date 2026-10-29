import unittest
from unittest.mock import patch
import games
class Baccarat(unittest.TestCase):
 def play(self,cards,choice='player'):
  with patch.object(games.odds,'deck',return_value=list(reversed(cards))):return games.start('baccarat',choice)
 def test_naturals_and_tie_refunds(self):
  self.assertEqual(self.play([4,3,4,4])['mult'],2)
  self.assertEqual(self.play([4,3,4,4],'banker')['mult'],0)
  self.assertEqual(self.play([3,4,4,4],'banker')['mult'],1.95)
  for choice,mult in [('player',1),('banker',1),('tie',9)]:self.assertEqual(self.play([4,4,4,4],choice)['mult'],mult)
 def test_banker_third_card_table(self):
  for banker in range(8):
   for third in range(10):
    # player initial 0, banker initial 0..7, then player third.
    r=self.play([10,10,10,banker or 10,third or 10,1])
    should=banker<=2 or banker==3 and third!=8 or banker==4 and 2<=third<=7 or banker==5 and 4<=third<=7 or banker==6 and third in (6,7)
    self.assertEqual(len(r['dealer']),3 if should else 2,(banker,third))
 def test_player_stands_banker_draws_through_five(self):
  for banker in range(8):
   r=self.play([3,10,3,banker or 10,1])
   self.assertEqual(len(r['player']),2)
   self.assertEqual(len(r['dealer']),3 if banker<=5 else 2)
