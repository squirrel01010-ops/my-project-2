import tempfile,unittest,time,sqlite3
from unittest.mock import patch
import core,bot
class Operations(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.db=patch.object(core,'DB',self.tmp.name+'/test.db');self.db.start();core.init()
 def tearDown(self):self.db.stop();self.tmp.cleanup()
 def test_persisted_chat_failure_recovers_and_crash_replay_does_not_double_pay(self):
  payload=dict(uid='123',name='user',channel='1',roles=[],category='',stamp=time.time())
  core.queue_chat('message',payload)
  with patch.object(core,'activity',side_effect=sqlite3.OperationalError('locked')):self.assertFalse(core.deliver_chat('message'))
  self.assertEqual(core.chat_health()['pending'],1)
  core.operate('admin','settings',dict(chatXP=999,key='change'),True)
  with core.db(True) as c:c.execute('UPDATE chat_inbox SET next_retry=0')
  self.assertEqual(core.recover_chat(),1)
  self.assertEqual(core.chat_health()['pending'],0)
  # Emulate a process exit after payment but before acknowledgement.
  with core.db(True) as c:c.execute("UPDATE chat_inbox SET status='processing',payload=?,next_retry=0",(__import__('json').dumps(payload),))
  core.recover_chat()
  with core.db() as c:self.assertEqual(core.user(c,'123')['xp'],25)
 def test_expired_resume_and_shop_pages(self):
  core.operate('a','adjust',dict(amount=1000,key='fund'),True)
  r=core.operate('a','play',dict(game='mines',bet=10,key='game'),True)
  with core.db(True) as c:c.execute('UPDATE game_rounds SET expires=0')
  self.assertIsNone(core.resume_game('a'))
  for i in range(26):core.operate('a','product',dict(name=str(i),kind='role',role_id=str(i+1),price=10,key='product'+str(i)),True)
  self.assertEqual(len(core.shop_catalog('a',3)['products']),6)
 def test_command_names_remain_flat_without_category_tags(self):
  self.assertIsNotNone(bot.tree.get_command('슬롯'))
  self.assertFalse(any(c.description.startswith(('[게임]','[기능]','[관리]')) for c in bot.tree.get_commands()))
  self.assertFalse(any(isinstance(c,bot.app_commands.Group) for c in bot.tree.get_commands()))
 def test_section_skips_unrelated_data(self):
  s=core.state('a',True,'settings')
  self.assertEqual(s['users'],[]);self.assertEqual(s['orders'],[]);self.assertEqual(s['rankings'],{})
