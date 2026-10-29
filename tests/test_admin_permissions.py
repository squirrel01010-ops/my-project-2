import tempfile,unittest
from unittest.mock import patch
import core,app
class AdminPermissions(unittest.TestCase):
 def test_live_role_permission(self):
  def api(path,*args,**kwargs):
   if '/members/' in path:return {'roles':['5']}
   if path.endswith('/roles'):return [{'id':'5','permissions':'8'}]
   return {'owner_id':'999'}
  with patch.object(app,'discord_api',side_effect=api),patch.object(app,'BOT_TOKEN','test'),patch.object(app,'GUILD','1'):
   self.assertTrue(app.membership('123')[1])
  def noadmin(path,*args,**kwargs):
   if path.endswith('/roles'):return [{'id':'5','permissions':'32'}]
   return api(path)
  with patch.object(app,'discord_api',side_effect=noadmin),patch.object(app,'BOT_TOKEN','test'),patch.object(app,'GUILD','1'):
   self.assertFalse(app.membership('123')[1])
 def test_other_member_adjustments(self):
  with tempfile.TemporaryDirectory() as d,patch.object(core,'DB',d+'/test.db'):
   core.init()
   with self.assertRaises(PermissionError):core.operate('123','adjust',{'id':'456','amount':100,'key':'denied'})
   r=core.operate('123','adjust',{'id':'456','amount':100,'key':'give'},True);self.assertEqual(r['xp'],100)
   r=core.operate('123','adjust',{'id':'456','amount':20,'mode':'set','key':'set'},True);self.assertEqual(r['xp'],20)
   r=core.operate('123','adjust',{'id':'456','amount':-5,'key':'take'},True);self.assertEqual(r['xp'],15)
