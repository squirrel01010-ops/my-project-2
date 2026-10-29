import unittest,tempfile
from unittest.mock import patch
import core,games
class RoulettePayout(unittest.TestCase):
 def test_custom_payout_and_fee(self):
  with tempfile.TemporaryDirectory() as d,patch.object(core,'DB',d+'/test.db'):
   core.init();core.operate('a','adjust',dict(id='a',amount=10000,key='f'),True)
   with core.db() as c:s=core.settings(c)
   s['games']['roulette'].update(redMultiplier=3.5,blackMultiplier=4,zeroMultiplier=50,fee=10)
   core.operate('a','settings',dict(games=s['games'],key='s'),True)
   with patch.object(games.RNG,'randrange',return_value=1):r=core.operate('a','play',dict(game='roulette',bet=100,choice='red',key='p'),True)
   self.assertEqual(r['payout'],325)
   self.assertEqual(r['state']['multipliers']['red'],3.5)
   with patch.object(games.RNG,'randrange',return_value=0):self.assertEqual(games.start('roulette','zero',s['games']['roulette'])['mult'],50)
   s['games']['roulette']['redMultiplier']=float('nan')
   with self.assertRaises(ValueError):core.validate_settings(s)
