import asyncio,sqlite3,tempfile,unittest,time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import patch,AsyncMock
import core,bot
class ChatDelivery(unittest.IsolatedAsyncioTestCase):
 async def test_lock_retry_and_uncached_author(self):
  message=SimpleNamespace(id=123,guild=SimpleNamespace(id=456),author=SimpleNamespace(id=789,bot=False,display_name='tester'),channel=SimpleNamespace(id=10,parent=SimpleNamespace(category_id=20)))
  with patch.object(bot,'GUILD_ID',456),patch.object(core,'activity',side_effect=[sqlite3.OperationalError('database is locked'),25]) as activity,patch.object(bot.asyncio,'sleep',new_callable=AsyncMock):
   await bot.on_message(message)
   self.assertEqual(activity.call_count,2)
   self.assertEqual(activity.call_args_list[0],activity.call_args_list[1])
   self.assertEqual(activity.call_args.kwargs['message_id'],123)
 def test_concurrent_burst_and_replays_paid_exactly_once(self):
  with tempfile.TemporaryDirectory() as d,patch.object(core,'DB',d+'/burst.db'):
   core.init()
   def send(i):return core.activity(str(i%20),'member','chat','1',message_id=str(i))
   with ThreadPoolExecutor(max_workers=16) as pool:list(pool.map(send,list(range(500))*2))
   with core.db() as c:
    self.assertEqual(c.execute('SELECT SUM(xp) FROM users').fetchone()[0],500*25)
    self.assertEqual(c.execute('SELECT SUM(amount) FROM activity').fetchone()[0],500)
    self.assertEqual(c.execute('SELECT COUNT(*) FROM chat_messages').fetchone()[0],500)
   with patch.object(core,'settings',wraps=core.settings) as settings:
    send(501);self.assertEqual(settings.call_count,1)
