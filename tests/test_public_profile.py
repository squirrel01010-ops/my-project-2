import tempfile,unittest
from types import SimpleNamespace
from unittest.mock import patch,AsyncMock
import bot,core
class PublicProfile(unittest.IsolatedAsyncioTestCase):
 async def test_public_self_and_other_profile_without_moving_coins(self):
  with tempfile.TemporaryDirectory() as d,patch.object(core,'DB',d+'/test.db'),patch.object(bot,'GUILD_ID',1):
   core.init();core.operate('admin','adjust',dict(id='2',name='other',amount=250,key='fund'),True)
   caller=SimpleNamespace(id=3,display_name='caller');target=SimpleNamespace(id=2,display_name='other')
   i=SimpleNamespace(guild_id=1,user=caller,response=SimpleNamespace(defer=AsyncMock()),followup=SimpleNamespace(send=AsyncMock()))
   await bot.profile.callback(i,target)
   i.response.defer.assert_awaited_once_with();kwargs=i.followup.send.await_args.kwargs
   self.assertFalse(kwargs.get('ephemeral',False));self.assertEqual(kwargs['embed'].title,'🪪 other');self.assertIn('250',kwargs['embed'].description)
   self.assertEqual([b.label for b in kwargs['view'].children],['📊 전적'])
   await kwargs['view'].children[0].callback(i)
   self.assertIn('other',i.followup.send.await_args.kwargs['embed'].title)
   with core.db() as c:self.assertEqual(core.user(c,'2')['xp'],250)
   await bot.profile.callback(i);self.assertEqual(i.followup.send.await_args.kwargs['embed'].title,'🪪 caller')
   self.assertIsNone(bot.tree.get_command('내정보'));self.assertIsNotNone(bot.tree.get_command('정보'))
