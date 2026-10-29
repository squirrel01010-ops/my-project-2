import tempfile,unittest,copy
from unittest.mock import patch
import games,core,bot
class ConfigurableGames(unittest.TestCase):
 def test_probability_extremes_and_consistent_results(self):
  for game,choice in [('coin','odd'),('dice',3),('roulette','red'),('horse',2),('slots',None),('scratch',None)]:
   for chance in (0,100):
    for _ in range(5):
     s=games.start(game,choice,{'winChance':chance,'winMultiplier':7})
     self.assertEqual(s['mult'],7 if chance else 0,(game,chance))
     if game=='coin':self.assertEqual(s['roll']%2==1,bool(chance))
     if game=='dice':self.assertEqual(s['roll']==3,bool(chance))
     if game=='roulette':self.assertEqual(s['roll'] in games.RED,bool(chance))
     if game=='horse':self.assertEqual(s['order'][0]==2,bool(chance));self.assertEqual(len(set(s['order'])),5)
     if game in ('slots','scratch'):self.assertEqual(len(set(s['symbols']))==1,bool(chance))
 def test_wheel_weights(self):
  for target in range(8):
   weights=[0]*8;weights[target]=1
   s=games.start('wheel',config={'wheelWeights':weights,'wheelMultipliers':list(range(8))})
   self.assertEqual(s['segment'],target);self.assertEqual(s['mult'],target)
 def test_settings_validation(self):
  for key,value in [('winChance',float('nan')),('winChance',101),('winMultiplier',-1),('profitScale',float('inf'))]:
   s=copy.deepcopy(core.DEFAULTS);s['games']['coin'][key]=value
   with self.assertRaises(ValueError):core.validate_settings(s)
  s=copy.deepcopy(core.DEFAULTS);s['games']['wheel']['wheelWeights']=[0]*8
  with self.assertRaises(ValueError):core.validate_settings(s)
 def test_running_round_keeps_original_profit_scale(self):
  with tempfile.TemporaryDirectory() as d,patch.object(core,'DB',d+'/test.db'):
   core.init();core.operate('123','adjust',dict(amount=10000,key='fund'),True)
   s=copy.deepcopy(core.DEFAULTS);s['games']['highlow']['profitScale']=3
   core.operate('123','settings',{**s,'key':'settings'},True)
   r=core.operate('123','play',dict(game='highlow',bet=100,key='start'))
   self.assertEqual(r['state']['profitScale'],3)
   s['games']['highlow']['profitScale']=8
   core.operate('123','settings',{**s,'key':'settings2'},True)
   with core.db(True) as c:
    row=c.execute('SELECT * FROM game_rounds WHERE id=?',(r['id'],)).fetchone()
    state={**r['state'],'done':True,'mult':2};core.settle(c,row,state)
    payout=c.execute('SELECT payout FROM game_rounds WHERE id=?',(r['id'],)).fetchone()[0]
   self.assertEqual(payout,400)
