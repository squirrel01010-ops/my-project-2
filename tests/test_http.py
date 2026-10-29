import hashlib
import http.client
import json
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import app
import core

class HTTP(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory();core.DB=cls.temp.name+'/http.db';core.init();app.ADMIN_TOKEN='test-only-token';app.ORIGIN='http://localhost'
  cls.server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler);cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
 @classmethod
 def tearDownClass(cls):cls.server.shutdown();cls.server.server_close();cls.thread.join();cls.temp.cleanup()
 def request(self,path,body=None,headers=None):
  c=http.client.HTTPConnection('127.0.0.1',self.server.server_port);c.request('POST' if body is not None else 'GET',path,json.dumps(body) if body is not None else None,headers or {});r=c.getresponse();raw=r.read();result=(r.status,raw,dict(r.getheaders()));c.close();return result
 def test_static_and_security_headers(self):
  status,raw,headers=self.request('/');self.assertEqual(status,200);self.assertIn(b'ORBIT',raw);self.assertIn('Content-Security-Policy',headers)
 def test_unauthenticated_and_cross_origin_denied(self):
  self.assertEqual(self.request('/api/state')[0],403)
  self.assertEqual(self.request('/api/adjust',dict(id='333',amount=10,key='x'),{'Authorization':'Bearer test-only-token','Origin':'https://evil.invalid'})[0],403)
 def test_admin_round_trip_and_sql_payload_safe(self):
  h={'Authorization':'Bearer test-only-token'}
  self.assertEqual(self.request('/api/adjust',dict(id='333',name="<script>alert(1)</script>",amount=1000,key='setup'),h)[0],200)
  status,raw,_=self.request('/api/state',headers=h);self.assertEqual(status,200);d=json.loads(raw);self.assertTrue(d['identity']['admin']);self.assertEqual(d['users'][0]['xp'],1000)
  self.assertEqual(self.request('/api/export',headers=h)[0],200)
 def test_member_csrf_and_admin_routes(self):
  with core.db(True) as c:
   core.ensure(c,'444','member');c.execute('INSERT OR REPLACE INTO sessions VALUES(?,?,?,?,?)',(app.digest('cookie'),'444','member','csrf',time.time()+60))
  h={'Cookie':'orbit_session=cookie'}
  with patch.object(app,'membership',return_value=({'roles':[]},False)):
   self.assertEqual(self.request('/api/attendance',dict(key='attend'),h)[0],403)
   h['X-CSRF-Token']='csrf'
   self.assertEqual(self.request('/api/adjust',dict(key='adjust',amount=100),h)[0],403)
   self.assertEqual(self.request('/api/attendance',dict(key='attend'),h)[0],200)
   self.assertEqual(self.request('/api/export',headers=h)[0],403)
 def test_oauth_state_mismatch(self):
  self.assertEqual(self.request('/auth/callback?state=forged&code=no')[0],403)
 def test_hidden_game_data_http(self):
  h={'Authorization':'Bearer test-only-token'}
  self.request('/api/adjust',dict(id='555',amount=1000,key='setup555'),h)
  status,raw,_=self.request('/api/play',dict(id='555',game='mines',bet=10,key='mine555'),h)
  self.assertEqual(status,200);self.assertNotIn('hazards',json.loads(raw)['state'])

# Discord links use the same cookie and per-request role checks as OAuth.
 def test_discord_link_login_and_single_use(self):
  token=core.issue_login_link('666','discord-member')
  with patch.object(app,'membership',return_value=({'roles':[]},True)):
   status,raw,h=self.request('/auth/discord-link',{'token':token})
   self.assertEqual(status,200)
   cookie=h['Set-Cookie'].split(';')[0];self.assertIn('HttpOnly',h['Set-Cookie'])
   status,raw,_=self.request('/api/state',headers={'Cookie':cookie})
   self.assertEqual(status,200);self.assertTrue(json.loads(raw)['identity']['admin'])
   self.assertEqual(json.loads(raw)['identity']['id'],'666')
   self.assertEqual(self.request('/auth/discord-link',{'token':token})[0],403)
  with patch.object(app,'membership',return_value=({'roles':[]},False)):
   status,raw,_=self.request('/api/state',headers={'Cookie':cookie})
   self.assertEqual(status,200);self.assertFalse(json.loads(raw)['identity']['admin'])
 def test_discord_link_expired_wrong_origin_and_nonmember(self):
  token=core.issue_login_link('777','member')
  self.assertEqual(self.request('/auth/discord-link',{'token':token},{'Origin':'https://evil.invalid'})[0],403)
  with patch.object(app,'membership',side_effect=PermissionError('not a member')):
   self.assertEqual(self.request('/auth/discord-link',{'token':token})[0],403)
  with core.db(True) as c:c.execute('UPDATE login_links SET expires=0 WHERE uid=?',('777',))
  self.assertEqual(self.request('/auth/discord-link',{'token':token})[0],403)

if __name__=='__main__':unittest.main()
