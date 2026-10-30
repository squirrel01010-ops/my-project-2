import tempfile,unittest,json
from unittest.mock import patch
from types import SimpleNamespace
from datetime import datetime,timezone
import bot,core
class ChatFallback(unittest.IsolatedAsyncioTestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.db=patch.object(core,'DB',self.tmp.name+'/test.db');self.db.start();self.guild=patch.object(bot,'GUILD_ID',456);self.guild.start();core.init()
 def tearDown(self):self.guild.stop();self.db.stop();self.tmp.cleanup()
 def message(self,n):return SimpleNamespace(id=n,guild=SimpleNamespace(id=456),author=SimpleNamespace(id=789,bot=False,display_name='user',roles=[]),channel=SimpleNamespace(id=10),created_at=datetime.now(timezone.utc))
 async def test_raw_gateway_and_high_level_event_pay_once(self):
  with patch.object(bot.client,'get_channel',return_value=None):
   await bot.on_socket_raw_receive(json.dumps(dict(t='MESSAGE_CREATE',d=dict(id='1000',guild_id='456',channel_id='10',author=dict(id='789',username='user'),timestamp=datetime.now(timezone.utc).isoformat()))))
  await bot.on_message(self.message(1000))
  with core.db() as c:self.assertEqual(core.user(c,'789')['xp'],25)
  self.assertEqual(core.chat_diagnostic('789','10')['messages'],1)
 async def test_history_recovers_missing_gateway_events_and_keeps_cursor(self):
  messages=[self.message(n) for n in range(1001,1004)]
  class Channel:
   id=10
   async def history(self,**kwargs):
    for message in messages:
     if message.id>kwargs['after'].id:yield message
  with patch.object(bot,'CHAT_STARTED',1000):
   await bot.on_message(messages[0]);await bot.recover_channel_chat(Channel());await bot.recover_channel_chat(Channel())
  with core.db() as c:
   self.assertEqual(core.user(c,'789')['xp'],75)
   self.assertEqual(c.execute("SELECT value FROM meta WHERE key='chat-cursor:456:10'").fetchone()[0],'1003')
 async def test_failed_enqueue_does_not_skip_history_message(self):
  message=self.message(1001)
  class Channel:
   id=10
   async def history(self,**kwargs):
    if kwargs['after'].id<1001:yield message
  with patch.object(bot,'CHAT_STARTED',1000),patch.object(bot,'enqueue_chat',side_effect=RuntimeError('unavailable')):
   with self.assertRaises(RuntimeError):await bot.recover_channel_chat(Channel())
  with core.db() as c:self.assertEqual(c.execute("SELECT value FROM meta WHERE key='chat-cursor:456:10'").fetchone()[0],'1000')
  await bot.recover_channel_chat(Channel())
  with core.db() as c:self.assertEqual(core.user(c,'789')['xp'],25)
