import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock,patch
import bot,games,game_motion
class StartScreen(unittest.IsolatedAsyncioTestCase):
 async def test_interactive_games_show_controls_without_fake_action(self):
  for game,(_,_,interactive) in games.CATALOG.items():
   choice={'coin':'odd','dice':1,'roulette':'red','horse':1}.get(game)
   state=games.start(game,choice)
   r=dict(id='test',revision=0,game=game,bet=10,fee=0,payout=0,status='done' if state['done'] else 'active',state=games.public_view(state))
   i=SimpleNamespace(response=SimpleNamespace(defer=AsyncMock()),edit_original_response=AsyncMock())
   with patch.object(bot,'operation',new=AsyncMock(return_value=r)),patch.object(bot,'decorate_round',new=AsyncMock(return_value=r)),patch.object(game_motion,'reveal',new=AsyncMock()) as motion:
    await bot.start_game(i,game,10,choice)
   if interactive:
    motion.assert_not_awaited();i.edit_original_response.assert_awaited_once()
    if not state['done']:self.assertGreater(len(i.edit_original_response.await_args.kwargs['view'].children),0)
    self.assertEqual(game_motion.sequence(r),[])
   else:motion.assert_awaited_once()
 def test_bomb_only_animates_after_a_wire_is_selected(self):
  r=dict(game='bomb',status='active',state=dict(opened=[],step=0))
  self.assertEqual(game_motion.sequence(r),[])
  r['previous_state']={'opened':[]};r['state']['opened']=[3]
  frames=game_motion.sequence(r)
  self.assertTrue(frames);self.assertIn('4번 전선',frames[0][0]);self.assertNotIn('1번 전선',frames[0][0])
