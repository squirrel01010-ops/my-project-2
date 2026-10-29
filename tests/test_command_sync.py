import json
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import app
import bot
import core
import discord


class CommandSync(unittest.IsolatedAsyncioTestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory()
  self.db=patch.object(core,'DB',self.tmp.name+'/sync.db');self.db.start();core.init()
  self.flag=patch.object(bot,'commands_synced',False);self.flag.start()
  self.guild=patch.object(bot,'GUILD_ID',456);self.guild.start()

 def tearDown(self):
  self.guild.stop();self.flag.stop();self.db.stop();self.tmp.cleanup()

 def status(self):
  with core.db() as c:return json.loads(c.execute("SELECT value FROM meta WHERE key='command_sync'").fetchone()[0])

 async def test_registers_every_command_and_honors_manual_request(self):
  expected=bot.tree.get_commands()
  with patch.object(bot.client,'is_ready',return_value=True),patch.object(bot.client,'get_guild',return_value=object()),patch.object(bot.tree,'sync',new_callable=AsyncMock,return_value=expected) as sync:
   await bot.sync_commands.coro()
   status=self.status();self.assertEqual(status['state'],'synced')
   for name in ('출석','게임','도박','홀짝','슬롯','홀덤','복권','크래시'):self.assertIn(name,status['names'])
   await bot.sync_commands.coro();self.assertEqual(sync.await_count,1)
   with core.db(True) as c:c.execute("INSERT INTO meta VALUES('command_sync_request','retry')")
   await bot.sync_commands.coro();self.assertEqual(sync.await_count,2)
   self.assertEqual(self.status()['request'],'retry')

 async def test_failed_registration_is_visible_and_retries(self):
  forbidden=discord.Forbidden(SimpleNamespace(status=403,reason='Forbidden'),{'message':'Missing Access','code':50001})
  with patch.object(bot.client,'is_ready',return_value=True),patch.object(bot.client,'get_guild',return_value=object()),patch.object(bot.tree,'sync',new_callable=AsyncMock,side_effect=[forbidden,bot.tree.get_commands()]):
   await bot.sync_commands.coro();self.assertEqual(self.status()['state'],'error')
   self.assertIn('권한',self.status()['message']);self.assertFalse(bot.commands_synced)
   await bot.sync_commands.coro();self.assertEqual(self.status()['state'],'synced')

 async def test_wrong_guild_does_not_register_elsewhere(self):
  with patch.object(bot.client,'is_ready',return_value=True),patch.object(bot.client,'get_guild',return_value=None),patch.object(bot.tree,'sync',new_callable=AsyncMock) as sync:
   await bot.sync_commands.coro();sync.assert_not_awaited()
   self.assertIn('서버 ID',self.status()['message'])

 def test_pending_status_and_invite_include_command_scope(self):
  with patch.object(app,'CLIENT','123'),patch.object(app,'GUILD','456'):
   with core.db(True) as c:c.execute("INSERT INTO meta VALUES('command_sync_request','new')")
   result=app.bot_status();self.assertEqual(result['state'],'pending')
   self.assertIn('applications.commands',result['invite']);self.assertIn('guild_id=456',result['invite'])

 async def test_missing_intent_reports_actionable_error(self):
  with core.db(True) as c:c.execute("INSERT INTO meta VALUES('command_sync_request','pending-retry')")
  with patch.dict('os.environ',{'DISCORD_TOKEN':'test-only'}),patch.object(bot.client,'login',new_callable=AsyncMock),patch.object(bot.client,'connect',new_callable=AsyncMock,side_effect=discord.PrivilegedIntentsRequired(None)),patch.object(bot.client,'__aenter__',new_callable=AsyncMock),patch.object(bot.client,'__aexit__',new_callable=AsyncMock):
   with self.assertRaises(SystemExit):await bot.main()
  self.assertIn('Server Members Intent',self.status()['message'])
  self.assertEqual(app.bot_status()['state'],'error')
