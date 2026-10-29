import tempfile,unittest
from unittest.mock import patch
import core,games,bot,social_bot
class NoBetCap(unittest.TestCase):
 def test_all_games_accept_above_old_cap_and_reject_over_balance(self):
  for game in list(games.CATALOG)+['holdem','crash']:
   with self.subTest(game=game),tempfile.TemporaryDirectory() as d,patch.object(core,'DB',d+'/test.db'):
    core.init();core.operate('a','adjust',dict(id='a',amount=5000000,key='fund'),True)
    path='holdem/create' if game=='holdem' else 'crash/join' if game=='crash' else 'play'
    body=dict(game=game,bet=2000000,buyin=2000000,blind=20,choice={'coin':'odd','dice':1,'roulette':'red','horse':1}.get(game),auto=200,key='large')
    core.operate('a',path,body,True)
    with self.assertRaises(ValueError):core.operate('a',path,{**body,'bet':10**30,'buyin':10**30,'key':'huge'},True)
 def test_slash_wagers_have_no_maximum(self):
  for cmd in bot.tree.get_commands():
   for p in cmd.parameters:
    if p.name in ('베팅','바이인'):self.assertIsNone(p.max_value)
