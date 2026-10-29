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

 def test_wheel_stops_on_actual_segment_and_keeps_duration(self):
  for target in range(8):
   steps=game_motion.sequence({'game':'wheel','state':{'segment':target}})
   self.assertEqual(steps[-1][0],game_motion.wheel_board(target))
   self.assertAlmostEqual(sum(delay for _,delay in steps),10)
   self.assertGreater(steps[-1][1],steps[0][1])
