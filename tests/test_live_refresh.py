import json,tempfile,time,unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock,patch
import core,social,social_bot
class LiveRefresh(unittest.IsolatedAsyncioTestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.db=patch.object(core,'DB',self.temp.name+'/test.db');self.db.start();core.init()
  self.state=dict(id='test-round',kind='crash',status='flying',created=100,starts=100,channel='1',commitment='hash',max_bet=1000,min_bet=1,crash=1000,seed='seed',players=[])
  self.row=dict(id='test-round',state=json.dumps(self.state),channel='1',message='2')
  self.message=SimpleNamespace(edit=AsyncMock());self.channel=SimpleNamespace(get_partial_message=lambda _:self.message)
  self.client=SimpleNamespace(get_channel=lambda _:self.channel,fetch_channel=AsyncMock(return_value=self.channel),is_ready=lambda:True)
 def tearDown(self):self.db.stop();self.temp.cleanup()
 async def test_multiplier_updates_without_any_interaction(self):
  with patch.object(social_bot,'CLIENT',self.client),patch.object(social.time,'time',return_value=101):await social_bot.refresh_live_message(self.row)
  first=self.message.edit.await_args.kwargs['embed'].description
  with patch.object(social_bot,'CLIENT',self.client),patch.object(social.time,'time',return_value=102):await social_bot.refresh_live_message(self.row)
  second=self.message.edit.await_args.kwargs['embed'].description
  self.assertNotEqual(first,second);self.assertEqual(self.message.edit.await_count,2)
  self.assertNotIn('새로고침',[x.label for x in self.message.edit.await_args.kwargs['view'].children])
 async def test_uncached_channel_is_fetched(self):
  self.client.get_channel=lambda _:None
  with patch.object(social_bot,'CLIENT',self.client):await social_bot.refresh_live_message(self.row)
  self.client.fetch_channel.assert_awaited_once_with(1);self.message.edit.assert_awaited_once()
 async def test_one_broken_message_does_not_block_other_games(self):
  with core.db(True) as c:
   c.execute('INSERT INTO live_games VALUES(?,?,?,?,?,?,?)',('broken','crash','{}','flying',time.time()+1,'1','2'))
   c.execute('INSERT INTO live_games VALUES(?,?,?,?,?,?,?)',('test-round','crash',self.row['state'],'flying',time.time(),'1','2'))
  with patch.object(social_bot,'CLIENT',self.client),patch.object(social_bot.asyncio,'to_thread',new=AsyncMock(return_value=None)):await social_bot.live_updates.coro()
  self.message.edit.assert_awaited_once()
 async def test_finished_round_is_not_edited_repeatedly(self):
  self.state['status']='done';self.row['state']=json.dumps(self.state)
  with patch.object(social_bot,'CLIENT',self.client):
   await social_bot.refresh_live_message(self.row);await social_bot.refresh_live_message(self.row)
  self.assertEqual(self.message.edit.await_count,1)
