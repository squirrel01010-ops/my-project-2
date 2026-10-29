import tempfile,unittest
from unittest.mock import AsyncMock,patch
import bot,core,games

class DiceModes(unittest.TestCase):
 def test_all_number_and_parity_results(self):
  for roll in range(1,7):
   for choice in [1,2,3,4,5,6,'odd','even']:
    with self.subTest(roll=roll,choice=choice),patch.object(games.RNG,'randint',return_value=roll):
     r=games.start('dice',choice)
     expected=(2 if (roll%2==1)==(choice=='odd') else 0) if isinstance(choice,str) else 6 if roll==choice else 0
     self.assertEqual(r['mult'],expected)
  for bad in [None,True,0,7,'wrong']:
   with self.assertRaises(ValueError):games.start('dice',bad)
 def test_both_modes_use_dice_weights_and_profit_fee(self):
  with tempfile.TemporaryDirectory() as d,patch.object(core,'DB',d+'/dice.db'):
   core.init();core.operate('a','adjust',dict(amount=1000,key='fund'),True)
   with core.db() as c:s=core.settings(c)
   s['games']['dice']['fee']=10
   core.operate('a','settings',dict(games=s['games'],probabilities={'dice':[0,0,1,0,0,0]},gameCooldown=0,key='settings'),True)
   for choice,payout in [(3,550),('odd',190),('even',0)]:
    result=core.operate('a','play',dict(game='dice',bet=100,choice=choice,key=str(choice)),True)
    self.assertEqual(result['state']['roll'],3);self.assertEqual(result['payout'],payout)

class DiceCommand(unittest.IsolatedAsyncioTestCase):
 async def test_routes_modes_and_rejects_missing_or_conflicting_choices(self):
  with patch.object(bot,'start_game',new_callable=AsyncMock) as start:
   await bot.dice_command.callback(None,100,'number',숫자=4)
   start.assert_awaited_with(None,'dice',100,4)
   await bot.dice_command.callback(None,100,'parity',홀짝='odd')
   start.assert_awaited_with(None,'dice',100,'odd')
   for mode,number,parity in [('number',None,None),('number',3,'odd'),('parity',None,None),('parity',2,'even'),('bad',None,None)]:
    with self.assertRaises(ValueError):await bot.dice_command.callback(None,100,mode,number,parity)
   self.assertEqual(start.await_count,2)
