import tempfile,unittest
from unittest.mock import patch,AsyncMock
import core,bot
class JobQueue(unittest.IsolatedAsyncioTestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.db=patch.object(core,'DB',self.tmp.name+'/jobs.db');self.db.start();core.init()
 def tearDown(self):self.db.stop();self.tmp.cleanup()
 async def test_pending_role_work_coalesces_but_new_work_survives_inflight_sync(self):
  with core.db(True) as c:
   for _ in range(100):core.job(c,'roles',dict(uid='123'))
   self.assertEqual(c.execute('SELECT COUNT(*) FROM jobs').fetchone()[0],1)
  async def sync(guild,uid):
   with core.db(True) as c:core.job(c,'roles',dict(uid=uid))
  with patch.object(bot,'sync_roles',side_effect=sync):await bot.process_jobs(object())
  with core.db() as c:
   self.assertEqual(c.execute("SELECT COUNT(*) FROM jobs WHERE status='pending'").fetchone()[0],1)
   self.assertEqual(c.execute("SELECT COUNT(*) FROM jobs WHERE status='done'").fetchone()[0],1)
 async def test_restart_recovers_claimed_work_and_does_not_coalesce_purchases(self):
  with core.db(True) as c:
   core.job(c,'roles',dict(uid='123'))
   c.execute("UPDATE jobs SET status='processing'")
   for _ in range(2):core.job(c,'purchase',dict(uid='123',order='order'))
  core.recover_jobs()
  with core.db() as c:
   self.assertEqual(c.execute("SELECT COUNT(*) FROM jobs WHERE status='pending'").fetchone()[0],3)
  with patch.object(bot,'sync_roles',new_callable=AsyncMock) as sync:
   await bot.process_jobs(object());sync.assert_awaited_once()
