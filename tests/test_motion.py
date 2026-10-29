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

 def test_custom_frames_end_on_the_real_result(self):
  for game,state in [('slots',{'symbols':[4,3,2]}),('scratch',{'symbols':[2,2,2]}),('blackjack',{'player':[1,10],'dealer':[9,10]}),('mines',{'opened':[1,2],'hazards':[0,3,4]}),('tower',{'step':3})]:
   r={'game':game,'state':state,'status':'done'}
   frames=game_motion.sequence(r)
   self.assertIn(game_motion.board(r),frames[-1][0])
   self.assertAlmostEqual(sum(delay for _,delay in frames),game_motion.DURATION[game])
   self.assertGreater(len(set(frame for frame,_ in frames)),2)
 def test_animation_does_not_change_game_state(self):
  import copy
  r={'game':'horse','state':{'order':[5,3,1,2,4]}}
  before=copy.deepcopy(r);frames=game_motion.sequence(r)
  self.assertEqual(r,before)
  finish=frames[-1][0]
  self.assertIn('5  '+ '─'*12+'▶',finish)
