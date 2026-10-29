import concurrent.futures
import importlib
import json
import os
import tempfile
import time
import unittest
from unittest.mock import patch
os.environ['DB_PATH']=tempfile.mktemp(suffix='.db')
import core
import games

class Economy(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();core.DB=self.tmp.name+'/test.db';core.init();self.seq=0
  self.op('adjust',dict(id='111',name='테스트 유저',amount=100000),admin=True)
  self.op('settings',dict(gameCooldown=0),admin=True)
 def tearDown(self):self.tmp.cleanup()
 def op(self,path,b,actor='111',admin=False):
  self.seq+=1;return core.operate(actor,path,dict(b,key=str(self.seq)),admin)
 def xp(self,uid='111'):
  with core.db() as c:return core.user(c,uid)['xp']
 def test_level_down_and_negative_rollback(self):
  self.op('adjust',dict(id='111',amount=-99900),admin=True)
  with core.db() as c:self.assertEqual(core.user(c,'111')['level'],1)
  with self.assertRaises(ValueError):self.op('adjust',dict(id='111',amount=-101),admin=True)
  self.assertEqual(self.xp(),100)
 def test_idempotency_and_payload_conflict(self):
  b=dict(id='111',amount=10,key='replayed');a=core.operate('admin','adjust',b,True);second=core.operate('admin','adjust',b,True)
  self.assertEqual(a,second);self.assertEqual(self.xp(),100010)
  with self.assertRaises(ValueError):core.operate('admin','adjust',{**b,'amount':20},True)
 def test_concurrent_double_spend(self):
  self.op('adjust',dict(id='111',amount=-99900),admin=True)
  def send(n):
   try:return core.operate('111','gift',dict(to='222',amount=80,key='parallel'+str(n)))
   except ValueError:return None
  with concurrent.futures.ThreadPoolExecutor(2) as ex:result=list(ex.map(send,[1,2]))
  self.assertEqual(sum(r is not None for r in result),1);self.assertEqual(self.xp(),20);self.assertEqual(self.xp('222'),80)
 def test_user_cannot_adjust_or_impersonate(self):
  with self.assertRaises(PermissionError):self.op('adjust',dict(amount=100,id='111'))
  self.op('attendance',dict(id='222'))
  with core.db() as c:self.assertIsNone(c.execute("SELECT 1 FROM attendance WHERE uid='222'").fetchone())
 def test_daily_attendance(self):
  result=self.op('attendance',{});self.assertEqual(result['streak'],1)
  with self.assertRaises(ValueError):self.op('attendance',{})
 def test_chat_ignores_exclusion_cap_and_cooldown(self):
  self.op('settings',dict(dailyCap=30,cooldown=60,excludedChannels=['999']),admin=True)
  self.assertEqual(core.activity('111','name','chat','999'),25)
  self.assertEqual(core.activity('111','name','chat','123'),25)
  self.assertEqual(core.activity('111','name','chat','123'),25)
  self.assertEqual(core.activity('111','name','chat','123'),25)
 def test_gift_fee(self):
  self.op('settings',dict(giftFee=10),admin=True);self.op('gift',dict(to='222',amount=100))
  self.assertEqual(self.xp(),99890);self.assertEqual(self.xp('222'),100)
 def test_game_ownership_and_revision(self):
  r=self.op('play',dict(game='mines',bet=100))
  self.assertNotIn('hazards',r['state'])
  with self.assertRaises(PermissionError):self.op('game/action',dict(round=r['id'],revision=0,action='pick',value=0),actor='222')
  with self.assertRaises(ValueError):self.op('game/action',dict(round=r['id'],revision=1,action='pick',value=0))
  with core.db() as c:st=json.loads(c.execute('SELECT state FROM game_rounds WHERE id=?',(r['id'],)).fetchone()[0])
  safe=next(n for n in range(9) if n not in st['hazards']);r=self.op('game/action',dict(round=r['id'],revision=0,action='pick',value=safe))
  self.assertEqual(r['revision'],1);r=self.op('game/action',dict(round=r['id'],revision=1,action='cashout'))
  self.assertEqual(r['payout'],150);self.assertEqual(self.xp(),100050)
 def test_admin_play_preserves_member_name(self):
  core.operate('local-admin','play',dict(id='111',game='coin',choice='odd',bet=10,key='admin-play'),True,dict(name='관리자'))
  with core.db() as c:self.assertEqual(core.user(c,'111')['name'],'테스트 유저')
 def test_one_game_at_a_time_timeout(self):
  r=self.op('play',dict(game='mines',bet=100))
  with self.assertRaises(ValueError):self.op('play',dict(game='bomb',bet=100))
  with core.db(True) as c:c.execute('UPDATE game_rounds SET expires=0 WHERE id=?',(r['id'],))
  core.maintenance();self.assertEqual(self.xp(),99900)
  with core.db() as c:self.assertEqual(c.execute('SELECT status FROM game_rounds').fetchone()[0],'done')
 def test_game_restrictions(self):
  self.op('settings',dict(casinoChannels=['999']),admin=True)
  with self.assertRaises(PermissionError):self.op('play',dict(game='coin',choice='odd',bet=100))
 def test_role_purchase_and_expiry(self):
  p=self.op('product',dict(name='역할',kind='role',price=100,stock=1,role_id='999',duration=60),admin=True)
  self.op('buy',dict(product_id=p['product_id']));want,_,_,_=core.desired_roles('111');self.assertIn('999',want)
  with self.assertRaises(ValueError):self.op('buy',dict(product_id=p['product_id']))
  with core.db(True) as c:c.execute('UPDATE orders SET expires=0')
  core.maintenance();want,_,_,_=core.desired_roles('111');self.assertNotIn('999',want)
 def test_code_delivery_single_use(self):
  p=self.op('product',dict(name='코드',kind='code',price=50,stock=-1),admin=True)
  self.op('inventory',dict(product_id=p['product_id'],codes=['SECRET-CODE']),admin=True)
  r=self.op('buy',dict(product_id=p['product_id']));self.assertEqual(r['code'],'SECRET-CODE')
  with self.assertRaises(ValueError):self.op('buy',dict(product_id=p['product_id']))
  self.assertEqual(self.xp(),99950);self.assertNotIn('SECRET-CODE',json.dumps(core.state('222')))
  self.assertNotIn('SECRET-CODE',json.dumps(core.state('admin',True)))
 def test_season_rewards_and_reset(self):
  self.op('settings',dict(seasonResetXP=True,seasonRewards=[dict(rank=1,xp=100,role='999')]),admin=True)
  self.op('season/end',dict(confirm='시즌 종료'),admin=True)
  self.assertEqual(self.xp(),100)
  state=core.state('111');self.assertEqual(len(state['seasons']),2);self.assertEqual(state['seasons'][1]['snapshot'][0]['score'],100000)
  self.assertIn('999',core.desired_roles('111')[0]);core.maintenance();self.assertEqual(len(core.state()['seasons']),2)
 def test_auto_season_and_role_revoke(self):
  self.op('settings',dict(roleRewards=[dict(type='level',threshold=10,role='777')]),admin=True)
  self.assertIn('777',core.desired_roles('111')[0])
  self.op('adjust',dict(id='111',amount=-99900),admin=True)
  self.assertNotIn('777',core.desired_roles('111')[0])
  self.op('settings',dict(seasonMode='monthly'),admin=True)
  with core.db(True) as c:c.execute("UPDATE seasons SET ends=1 WHERE status='active'")
  core.maintenance();self.assertEqual(len(core.state()['seasons']),2)
 def test_all_games_play_to_completion(self):
  for g in games.CATALOG:
   choice={'coin':'odd','dice':1,'roulette':'red','horse':1}.get(g)
   with self.subTest(game=g):
    r=self.op('play',dict(game=g,bet=100,choice=choice))
    while r['status']=='active':
     s=r['state'];act='pick';value=0
     if g=='blackjack':act='stand';value=None
     elif g=='indian':act='call';value=None
     elif g=='baskin':act='count';value=1
     elif g=='highlow':act='higher' if s['card']<13 else 'lower';value=None
     elif g in ('mines','bomb'):value=next(n for n in range(9 if g=='mines' else 5) if n not in s['opened'])
     elif g=='ttt':value=next(n for n in range(9) if not s['board'][n])
     r=self.op('game/action',dict(round=r['id'],revision=r['revision'],action=act,value=value))
    self.assertGreaterEqual(r['payout'],0)
 def test_invalid_settings_rollback(self):
  with self.assertRaises(ValueError):self.op('settings',dict(minBet=100,maxBet=1),admin=True)
  with core.db() as c:self.assertEqual(core.settings(c)['minBet'],10)

class Rules(unittest.TestCase):
 def test_hidden_information(self):
  s=games.start('indian');self.assertIsNone(games.public_view(s)['player'])
  s=games.start('mines');self.assertNotIn('hazards',games.public_view(s))
 def test_blackjack_aces_and_dealer(self):
  self.assertEqual(games.total([1,1,9]),21)
  s=dict(game='blackjack',done=False,player=[10,8],dealer=[10,6],deck=[10])
  games.action(s,'stand');self.assertEqual(s['mult'],2)
 def test_highlow_tie_loses(self):
  s=dict(game='highlow',done=False,card=5,step=0,mult=1)
  with patch.object(games.RNG,'randint',return_value=5):games.action(s,'higher')
  self.assertTrue(s['done']);self.assertEqual(s['mult'],0)

if __name__=='__main__':unittest.main()


class ChatCounting(unittest.TestCase):
 def test_message_replay_is_not_paid_twice_and_rapid_messages_all_count(self):
  with tempfile.TemporaryDirectory() as d,patch.object(core,'DB',d+'/chat.db'):
   core.init()
   with concurrent.futures.ThreadPoolExecutor(8) as pool:
    paid=list(pool.map(lambda n:core.activity('111','tester','chat','123',stamp=1000,message_id=n),range(30)))
   self.assertEqual(paid,[25]*30)
   self.assertEqual(core.activity('111','tester','chat','123',stamp=1001,message_id=0),0)
   with core.db() as c:
    self.assertEqual(core.user(c,'111')['xp'],750)
    self.assertEqual(c.execute("SELECT SUM(amount) FROM activity WHERE kind='chat'").fetchone()[0],30)
 def test_wheel_multiplier_icons_are_distinct(self):
  self.assertEqual(len({games.multiplier_badge(n).split()[0] for n in (0,1,2,4,36)}),5)
