import itertools,tempfile,unittest
from unittest.mock import patch
import core,games

class SlotSettings(unittest.TestCase):
 def test_all_125_combinations(self):
  config=dict(pairMultiplier=0.5,tripleMultipliers=[2,4,6,8,10])
  for symbols in itertools.product(range(5),repeat=3):
   with self.subTest(symbols=symbols),patch.object(games.RNG,'randrange',side_effect=symbols):
    s=games.start('slots',config=config)
    expected=config['tripleMultipliers'][symbols[0]] if len(set(symbols))==1 else 0.5 if len(set(symbols))==2 else 0
    self.assertEqual(s['mult'],expected)
    self.assertTrue(s['done'])
 def test_defaults_and_scratch_unchanged(self):
  with patch.object(games.RNG,'randrange',side_effect=[0,1,0]):self.assertEqual(games.start('slots')['mult'],0.5)
  with patch.object(games.RNG,'randrange',side_effect=[4,4,4]):self.assertEqual(games.start('slots')['mult'],40)
  with patch.object(games.RNG,'randrange',side_effect=[0,0,1]):self.assertEqual(games.start('scratch')['mult'],0)
 def test_saved_settings_payout_fee_replay_and_validation(self):
  with tempfile.TemporaryDirectory() as d,patch.object(core,'DB',d+'/slots.db'):
   core.init();core.operate('a','adjust',dict(id='a',amount=10000,key='fund'),True)
   with core.db() as c:s=core.settings(c)
   s['games']['slots'].update(pairMultiplier=0.5,tripleMultipliers=[2,3,4,5,6.5],fee=10)
   core.operate('a','settings',dict(games=s['games'],gameCooldown=0,key='settings'),True)
   for key,symbols,bet,expected in [('pair',[0,1,0],101,50),('triple',[4,4,4],100,595)]:
    body=dict(game='slots',bet=bet,key=key)
    with patch.object(games.RNG,'randrange',side_effect=symbols):r=core.operate('a','play',body,True)
    self.assertEqual(r['payout'],expected)
    self.assertEqual(core.operate('a','play',body,True)['id'],r['id'])
   with core.db() as c:self.assertEqual(core.user(c,'a')['xp'],10444)
   for invalid in [True,-1,1001,float('nan'),float('inf'),'2']:
    s['games']['slots']['pairMultiplier']=invalid
    with self.assertRaises(ValueError):core.validate_settings(s)
   s['games']['slots']['pairMultiplier']=0.5
   for invalid in [[],[1]*4,[1]*6,'12345',[1,2,3,4,None]]:
    s['games']['slots']['tripleMultipliers']=invalid
    with self.assertRaises(ValueError):core.validate_settings(s)
   with core.db() as c:self.assertEqual(core.settings(c)['games']['slots']['pairMultiplier'],0.5)
