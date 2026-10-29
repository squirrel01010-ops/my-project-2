import asyncio
import sqlite3
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import bot
import core


class Resilience(unittest.IsolatedAsyncioTestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory()
  self.db=patch.object(core,'DB',self.tmp.name+'/test.db');self.db.start();core.init()

 def tearDown(self):
  self.db.stop();self.tmp.cleanup()

 async def test_chat_recovery_loop_survives_database_lock(self):
  event=asyncio.Event();loop=asyncio.get_running_loop();calls=[]
  def recover():
   calls.append(1)
   if len(calls)==1:raise sqlite3.OperationalError('database is locked')
   loop.call_soon_threadsafe(event.set)
  task=bot.chat_recovery
  with patch.object(core,'recover_chat',side_effect=recover),patch('discord.ext.tasks.ExponentialBackoff.delay',return_value=.001):
   try:
    task.start()
    await asyncio.wait_for(event.wait(),2)
    self.assertTrue(task.is_running())
    self.assertFalse(task.failed())
   finally:
    task.cancel()
    await asyncio.gather(task.get_task(),return_exceptions=True)
  self.assertGreaterEqual(len(calls),2)

 async def test_profile_acknowledges_and_gateway_remains_responsive_during_lock(self):
  lock=sqlite3.connect(core.DB,check_same_thread=False);lock.execute('BEGIN IMMEDIATE')
  # Release even on regression, so a blocking implementation cannot hang the suite.
  timer=threading.Timer(.5,lock.rollback);timer.start()
  i=SimpleNamespace(guild_id=123,user=SimpleNamespace(id=456,display_name='tester'),response=SimpleNamespace(defer=AsyncMock()),followup=SimpleNamespace(send=AsyncMock()))
  with patch.object(bot,'GUILD_ID',123):
   task=asyncio.create_task(bot.profile.callback(i))
   try:
    await asyncio.sleep(.03)
    i.response.defer.assert_awaited_once_with(ephemeral=True)
    self.assertFalse(task.done(),'Database contention blocked the gateway event loop')
   finally:
    timer.cancel();timer.join();lock.rollback()
    await task;lock.close()
  i.followup.send.assert_awaited_once()

 async def test_resume_acknowledges_before_loading(self):
  i=SimpleNamespace(guild_id=123,user=SimpleNamespace(id=456),response=SimpleNamespace(defer=AsyncMock()),followup=SimpleNamespace(send=AsyncMock()))
  def read(uid):
   self.assertTrue(i.response.defer.await_count);return None
  with patch.object(bot,'GUILD_ID',123),patch.object(core,'resume_game',side_effect=read):
   await bot.resume.callback(i)
  i.followup.send.assert_awaited_once_with('진행 중인 게임이 없어요',ephemeral=True)

 def test_shop_out_of_range_pages_clamp_after_product_removal(self):
  self.assertEqual(core.shop_catalog('123',999)['page'],1)
  with core.db(True) as c:
   for n in range(11):c.execute("INSERT INTO products(name,price,kind,role_id,stock) VALUES(?,10,'role',?,-1)",(str(n),str(n)))
  last=core.shop_catalog('123',999)
  self.assertEqual((last['page'],last['pages'],len(last['products'])),(2,2,1))
  with core.db(True) as c:c.execute('UPDATE products SET active=0 WHERE id=11')
  self.assertEqual(core.shop_catalog('123',2)['page'],1)
