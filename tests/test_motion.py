import unittest
from unittest.mock import AsyncMock,patch
import discord
import games
import game_motion

class MotionTests(unittest.IsolatedAsyncioTestCase):
 async def test_every_game_finishes_with_real_result(self):
  for game in games.CATALOG:
   edit=AsyncMock();final=object();view=object()
   with patch('game_motion.asyncio.sleep',new_callable=AsyncMock):
    await game_motion.reveal(edit,{'game':game},final,view)
   self.assertEqual(edit.await_count,len(game_motion.sequence({'game':game}))+1)
   self.assertIs(edit.await_args.kwargs['embed'],final)
   self.assertIs(edit.await_args.kwargs['view'],view)
   for call in edit.await_args_list[:-1]:self.assertEqual(len(call.kwargs['view'].children),0)
 async def test_failed_frame_still_publishes_result(self):
  edit=AsyncMock(side_effect=[discord.NotFound(type('Response',(),{'status':404,'reason':'gone'})(),'gone'),None])
  final=object()
  await game_motion.reveal(edit,{'game':'slots'},final,None)
  self.assertIs(edit.await_args.kwargs['embed'],final)

 def test_all_final_frames_match_result(self):
  for game in games.CATALOG:
   choice={'coin':'odd','dice':1,'roulette':'red','horse':1}.get(game)
   s=games.public_view(games.start(game,choice))
   r={'game':game,'state':s,'status':'done' if s['done'] else 'active','previous_state':{}}
   seq=game_motion.sequence(r)
   if game not in ('wheel','roulette'):self.assertEqual(seq[-1][0],game_motion.board(r))
   else:
    index=s['segment'] if game=='wheel' else game_motion.ROULETTE_RING.index(s['roll'])
    self.assertEqual(seq[-1][0],game_motion.spin_frame(r,index))
    self.assertGreater(seq[-1][1],seq[0][1])
