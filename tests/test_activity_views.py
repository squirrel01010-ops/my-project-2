import tempfile,unittest,sqlite3
from unittest.mock import patch
import core
class ActivityViews(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.db=patch.object(core,'DB',self.tmp.name+'/data.db');self.db.start();core.init()
 def tearDown(self):self.db.stop();self.tmp.cleanup()
 def test_history_pagination_and_member_scope(self):
  for i in range(105):core.operate('a','adjust',dict(id='a',amount=1,reason='검사',key=str(i)),True)
  core.operate('b','adjust',dict(amount=1,key='b'),True)
  r=core.history('a',False,dict(uid='b',page=2,reason='검사'))
  self.assertEqual(len(r['rows']),50);self.assertEqual(r['total'],105)
  self.assertTrue(all(x['uid']=='a' for x in r['rows']))
  self.assertEqual(len(core.history('a',False,dict(page=3))['rows']),5)
  self.assertEqual(core.history('admin',True,dict(uid='b'))['total'],1)
 def test_personal_stats_and_health(self):
  core.activity('a','A','chat','1',message_id='1');core.activity('a','A','chat','1',message_id='1')
  core.activity('b','B','chat','1',message_id='2')
  r=core.personal_activity('a');self.assertEqual(r['earned'],25);self.assertEqual(r['days'][0]['amount'],1)
  health=core.chat_health();self.assertEqual(health['processed'],2);self.assertEqual(health['duplicates'],1)
  self.assertIsNotNone(health['last_paid']);core.chat_failure(sqlite3.OperationalError('secret data'))
  self.assertEqual(core.chat_health()['failures'],1);self.assertNotIn('secret',str(core.chat_health()))
 def test_light_poll_avoids_full_state_and_returns_private_cards(self):
  with patch.object(core,'state',side_effect=AssertionError('full state called')):
   result=core.social_state('a','lottery')
  self.assertEqual(set(result['social']),{'lottery','tickets'})
  self.assertNotIn('users',result);self.assertNotIn('ledger',result)
