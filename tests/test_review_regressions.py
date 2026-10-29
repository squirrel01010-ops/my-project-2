import tempfile
import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock,patch
import core
import bot

class EconomyRegressions(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.patch=patch.object(core,'DB',self.tmp.name+'/test.db');self.patch.start();core.init();self.serial=0
 def tearDown(self):self.patch.stop();self.tmp.cleanup()
 def op(self,path,**body):
  self.serial+=1
  return core.operate('admin',path,dict(body,key=str(self.serial)),True)
 def test_minimum_no_longer_blocked_by_obsolete_cap(self):
  self.op('settings',minBet=20000,maxBet=30000)
  with core.db() as c:self.assertEqual(core.settings(c)['minBet'],20000)
 def test_timezone_backwards_does_not_pay_another_attendance(self):
  with patch.object(core,'today',return_value=date(2026,10,30)):self.op('attendance')
  with patch.object(core,'today',return_value=date(2026,10,29)):
   with self.assertRaisesRegex(ValueError,'이미 출석'):self.op('attendance')
  with patch.object(core,'today',return_value=date(2026,10,31)):
   self.assertEqual(self.op('attendance')['streak'],2)
 def test_duplicate_codes_are_rejected_and_old_duplicate_stock_not_resold(self):
  self.op('adjust',id='buyer',amount=10000)
  pid=self.op('product',name='code',kind='code',price=100,stock=-1)['product_id']
  with self.assertRaisesRegex(ValueError,'중복'):self.op('inventory',product_id=pid,codes=['SAME','SAME'])
  self.op('inventory',product_id=pid,codes=['SAME'])
  with self.assertRaisesRegex(ValueError,'중복'):self.op('inventory',product_id=pid,codes=['SAME'])
  # Simulate duplicate stock created by a previous version.
  with core.db(True) as c:c.execute('INSERT INTO inventory(product_id,code) VALUES(?,?)',(pid,'SAME'))
  self.assertEqual(core.state('admin',True)['products'][0]['codes'],1)
  self.op('buy',id='buyer',product_id=pid)
  with self.assertRaisesRegex(ValueError,'코드 재고'):self.op('buy',id='buyer',product_id=pid)
  with core.db() as c:self.assertEqual(core.user(c,'buyer')['xp'],9900)
  self.assertEqual(core.state('admin',True)['products'][0]['codes'],0)

 def test_code_products_cannot_silently_grant_a_role(self):
  self.op('adjust',id='buyer',amount=1000)
  pid=self.op('product',name='code',kind='code',role_id='777',price=100,stock=-1)['product_id']
  self.op('inventory',product_id=pid,codes=['UNIQUE'])
  self.op('buy',id='buyer',product_id=pid)
  self.assertNotIn('777',core.desired_roles('buyer')[0])
 def test_same_second_backups_keep_both_complete_snapshots(self):
  import backup,sqlite3,os
  with patch.dict(os.environ,{'BACKUP_DIR':self.tmp.name+'/backups'}),patch.object(backup.time,'strftime',return_value='orbit-same-second'):
   self.op('adjust',id='buyer',amount=10)
   first=backup.create_backup()
   self.op('adjust',id='buyer',amount=5)
   second=backup.create_backup()
   self.assertNotEqual(first,second)
   for path,balance in ((first,10),(second,15)):
    with sqlite3.connect(path) as c:
     self.assertEqual(c.execute('PRAGMA quick_check').fetchone()[0],'ok')
     self.assertEqual(c.execute("SELECT xp FROM users WHERE id='buyer'").fetchone()[0],balance)
    self.assertEqual(path.stat().st_mode&0o777,0o600)

class ThreadNotifications(unittest.IsolatedAsyncioTestCase):
 async def test_discord_configured_admin_role_is_checked_on_every_request(self):
  with tempfile.TemporaryDirectory() as d,patch.object(core,'DB',d+'/admin.db'),patch.object(bot,'GUILD_ID',456):
   core.init()
   role=SimpleNamespace(id=5,permissions=SimpleNamespace(administrator=False))
   member=SimpleNamespace(roles=[role])
   guild=SimpleNamespace(owner_id=999,fetch_member=AsyncMock(return_value=member),fetch_roles=AsyncMock(return_value=[role]))
   i=SimpleNamespace(id=1,guild_id=456,guild=guild,channel_id=789,user=SimpleNamespace(id=123,display_name='manager',roles=[role]),response=SimpleNamespace(defer=AsyncMock()),followup=SimpleNamespace(send=AsyncMock()))
   target=SimpleNamespace(id=321,bot=False,display_name='buyer')
   command=bot.tree.get_command('포인트관리')
   self.assertIsNone(command.default_permissions)
   with self.assertRaises(PermissionError):await command.callback(i,target,'give',100)
   core.operate('admin','settings',dict(adminRoles=['5'],key='grant'),True)
   await command.callback(i,target,'give',100)
   core.operate('admin','settings',dict(adminRoles=[],key='revoke'),True)
   i.id=2
   with self.assertRaises(PermissionError):await command.callback(i,target,'give',100)
   with core.db() as c:self.assertEqual(core.user(c,'321')['xp'],100)

 async def test_notification_can_use_a_thread_channel(self):
  thread=SimpleNamespace(send=AsyncMock())
  guild=SimpleNamespace(get_channel_or_thread=lambda channel:thread if channel==123 else None)
  await bot.send_channel(guild,'123','hello',{'embedColor':'#aabbcc'})
  thread.send.assert_awaited_once()

class PurchaseDelivery(unittest.IsolatedAsyncioTestCase):
 async def test_uncached_buyer_gets_code_and_failed_delivery_can_retry(self):
  import discord
  with tempfile.TemporaryDirectory() as d,patch.object(core,'DB',d+'/delivery.db'):
   core.init()
   core.operate('admin','adjust',dict(id='123',amount=100,key='fund'),True)
   pid=core.operate('admin','product',dict(name='gift',kind='code',price=10,key='product'),True)['product_id']
   core.operate('admin','inventory',dict(product_id=pid,codes=['PRIVATE-CODE'],key='stock'),True)
   core.operate('123','buy',dict(product_id=pid,key='buy'))
   with core.db(True) as c:
    c.execute("UPDATE jobs SET status='done' WHERE kind!='purchase'")
    jid=c.execute("SELECT id FROM jobs WHERE kind='purchase'").fetchone()[0]
   member=SimpleNamespace(send=AsyncMock())
   error=discord.Forbidden(SimpleNamespace(status=403,reason='Forbidden'),{'message':'Cannot send messages'})
   guild=SimpleNamespace(get_member=lambda uid:None,fetch_member=AsyncMock(side_effect=error))
   await bot.process_jobs(guild)
   with core.db() as c:self.assertEqual(c.execute('SELECT status FROM jobs WHERE id=?',(jid,)).fetchone()[0],'failed')
   core.operate('admin','job/retry',dict(job_id=jid,key='retry'),True)
   guild.fetch_member=AsyncMock(return_value=member)
   await bot.process_jobs(guild)
   guild.fetch_member.assert_awaited_once_with(123)
   self.assertIn('PRIVATE-CODE',member.send.await_args.args[0])
   with core.db() as c:
    self.assertEqual(c.execute('SELECT status FROM jobs WHERE id=?',(jid,)).fetchone()[0],'done')
    self.assertEqual(core.user(c,'123')['xp'],90)
   await bot.process_jobs(guild)
   member.send.assert_awaited_once()

 async def test_ranking_acknowledges_before_loading_state(self):
  response=SimpleNamespace(defer=AsyncMock())
  i=SimpleNamespace(guild_id=456,response=response,followup=SimpleNamespace(send=AsyncMock()))
  def state():
   response.defer.assert_awaited_once()
   return {'users':[]}
  with patch.object(bot,'GUILD_ID',456),patch.object(core,'state',side_effect=state):
   await bot.tree.get_command('랭킹').callback(i)
  i.followup.send.assert_awaited_once()
