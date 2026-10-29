import concurrent.futures
import json
import random
import tempfile
import time
import unittest
from unittest.mock import patch
import core
import poker
import social

def card(rank,suit=0):return suit*13+rank-2

class PokerRules(unittest.TestCase):
 def test_hand_order_and_wheel(self):
  self.assertEqual(poker.rank5([card(r) for r in [14,2,3,4,5]]),(8,5))
  self.assertEqual(poker.rank5([card(14),card(14,1),card(14,2),card(13),card(13,1)]),(6,14,13))
  self.assertGreater(poker.rank5([card(14),card(14,1),card(14,2),card(14,3),card(2)]),poker.rank5([card(13),card(13,1),card(13,2),card(12),card(12,1)]))
 def test_side_pots(self):
  s=dict(players=[dict(uid='a',cards=[card(14),card(14,1)],total=100,stack=0,folded=False),dict(uid='b',cards=[card(13),card(13,1)],total=200,stack=0,folded=False),dict(uid='c',cards=[card(12),card(12,1)],total=300,stack=0,folded=False),dict(uid='d',cards=[card(11),card(11,1)],total=100,stack=0,folded=True)],dealer=0,board=[card(2,3),card(3,2),card(5,1),card(7),card(9,3)])
  poker.showdown(s);self.assertEqual(s['payouts'],dict(a=400,b=200,c=100,d=0))
 def test_split_pot_odd_chip(self):
  s=dict(players=[dict(uid='a',cards=[card(2,1),card(3,1)],total=10,stack=0,folded=False),dict(uid='b',cards=[card(4,1),card(5,1)],total=10,stack=0,folded=False),dict(uid='c',cards=[card(6,1),card(7,1)],total=1,stack=0,folded=True)],dealer=0,board=[card(r) for r in (10,11,12,13,14)])
  poker.showdown(s);self.assertEqual(s['payouts'],dict(a=10,b=11,c=0))
 def test_short_allin_does_not_reopen_raising(self):
  s=dict(status='active',turn=0,deadline=100,bet=150,min_raise=100,players=[dict(uid='a',stack=500,round=100,total=100,acted=100,folded=False)])
  with self.assertRaises(ValueError):poker.act(s,'a','raise',300,1)
 def test_heads_up_blinds_and_first_action(self):
  s=dict(players=[dict(uid=str(i),stack=1000) for i in range(2)],blind=20,turn_seconds=45)
  poker.begin(s,0);self.assertEqual(s['turn'],s['dealer']);self.assertEqual(s['players'][s['dealer']]['round'],10)
 def test_random_multiplayer_chip_conservation(self):
  rng=random.Random(2026)
  for n in range(2,7):
   for _ in range(20):
    s=dict(players=[dict(uid=str(i),stack=rng.choice([100,200,300])) for i in range(n)],blind=10,turn_seconds=45)
    total=sum(p['stack'] for p in s['players']);poker.begin(s,0);steps=0
    while s['status']=='active':
     steps+=1;self.assertLess(steps,100)
     p=s['players'][s['turn']];a=rng.choice(['call','fold','allin'])
     try:poker.act(s,p['uid'],a,None,1)
     except ValueError:poker.act(s,p['uid'],'call',None,1)
    self.assertEqual(sum(s['payouts'].values()),total);self.assertTrue(all(v>=0 for v in s['payouts'].values()))

class SocialTransactions(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();core.DB=self.temp.name+'/social.db';core.init();self.seq=0
  for uid in ('111','222','333'):self.op(uid,'adjust',dict(id=uid,amount=10000),True)
 def tearDown(self):self.temp.cleanup()
 def op(self,uid,path,b,admin=False):
  self.seq+=1;return core.operate(uid,path,dict(b,key='social'+str(self.seq)),admin,dict(name=uid,channel='777',roles=[]))
 def xp(self,uid):
  with core.db() as c:return core.user(c,uid)['xp']
 def raw(self,rid,kind):
  with core.db() as c:return social.load(c,rid,kind)
 def setraw(self,s):
  with core.db(True) as c:social.save(c,s)
 def table(self):
  s=self.op('111','holdem/create',dict(buyin=1000,blind=20));self.op('222','holdem/join',dict(table=s['id']));return self.op('111','holdem/start',dict(table=s['id']))
 def test_poker_private_cards_and_fold_payout(self):
  s=self.table();pub=social.read('holdem',s['id']);private=social.read('holdem',s['id'],'111')
  self.assertNotIn('deck',pub);self.assertEqual(pub['players'][0]['cards'],['🂠','🂠']);self.assertNotEqual(private['players'][0]['cards'],['🂠','🂠']);self.assertEqual(private['players'][1]['cards'],['🂠','🂠'])
  actor=s['players'][s['turn']]['uid'];s=self.op(actor,'holdem/action',dict(table=s['id'],revision=s['revision'],action='fold'))
  self.assertEqual(s['status'],'done');self.assertEqual(self.xp('111')+self.xp('222'),20000)
  before=self.xp('111');core.maintenance();core.maintenance();self.assertEqual(before,self.xp('111'))
 def test_poker_wrong_actor_stale_revision(self):
  s=self.table();actor=s['players'][s['turn']]['uid']
  with self.assertRaises(PermissionError):self.op('333','holdem/action',dict(table=s['id'],revision=s['revision'],action='fold'))
  with self.assertRaises(ValueError):self.op(actor,'holdem/action',dict(table=s['id'],revision=999,action='fold'))
 def test_lobby_timeout_refunds_and_duplicate_join(self):
  s=self.op('111','holdem/create',dict(buyin=1000,blind=20))
  with self.assertRaises(ValueError):self.op('111','holdem/join',dict(table=s['id']))
  raw=self.raw(s['id'],'holdem');raw['lobby_end']=1;self.setraw(raw);core.maintenance();self.assertEqual(self.xp('111'),10000);self.assertEqual(self.raw(s['id'],'holdem')['status'],'cancelled')
 def test_poker_timeout_and_restart(self):
  s=self.table();raw=self.raw(s['id'],'holdem');raw['deadline']=1;self.setraw(raw);core.init();core.maintenance()
  self.assertEqual(self.raw(s['id'],'holdem')['status'],'done');self.assertEqual(self.xp('111')+self.xp('222'),20000)
 def test_no_admin_hole_card_override(self):
  s=self.table();state=core.state('333',True);table=next(t for t in state['social']['holdem'] if t['id']==s['id']);self.assertTrue(all(p['cards']==['🂠','🂠'] for p in table['players']))
 def test_lottery_numbers_idempotency_and_draw(self):
  core.maintenance();d=social.read('lottery');payload=dict(draw=d['id'],numbers=[1,2,3],key='duplicate')
  r=core.operate('111','lottery/buy',payload,False,dict(channel='777'));self.assertEqual(r,core.operate('111','lottery/buy',payload,False,dict(channel='777')))
  self.assertEqual(self.xp('111'),9900)
  self.op('222','lottery/buy',dict(draw=d['id'],numbers=[1,2,3]));self.op('333','lottery/buy',dict(draw=d['id'],numbers=[4,5,6]))
  raw=self.raw(d['id'],'lottery');raw['draw_at']=1;self.setraw(raw)
  with patch('secrets.SystemRandom.sample',return_value=[1,2,3]):core.maintenance()
  done=social.read('lottery',d['id']);self.assertEqual(done['paid'],300);self.assertEqual(self.xp('111'),10050);self.assertEqual(self.xp('222'),10050);self.assertEqual(self.xp('333'),9900)
  core.maintenance();self.assertEqual(self.xp('111'),10050)
 def test_lottery_limit_invalid_and_stale_draw(self):
  core.maintenance();d=social.read('lottery')
  with self.assertRaises(ValueError):self.op('111','lottery/buy',dict(draw=d['id'],numbers=[1,1,2]))
  self.op('111','lottery/buy',dict(draw=d['id'],count=20))
  with self.assertRaises(ValueError):self.op('111','lottery/buy',dict(draw=d['id']))
  raw=self.raw(d['id'],'lottery');raw['draw_at']=1;self.setraw(raw)
  with self.assertRaises(ValueError):self.op('222','lottery/buy',dict(draw=d['id']))
 def test_lottery_rollover(self):
  core.maintenance();d=social.read('lottery');self.op('111','lottery/buy',dict(draw=d['id'],numbers=[1,2,3]));raw=self.raw(d['id'],'lottery');raw['draw_at']=1;self.setraw(raw)
  with patch('secrets.SystemRandom.sample',return_value=[4,5,6]):core.maintenance()
  self.assertEqual(social.read('lottery')['rollover'],100)
 def crash(self,auto=200):return self.op('111','crash/join',dict(bet=100,auto=auto))
 def test_crash_hidden_seed_and_automatic_after_restart(self):
  s=self.crash();self.assertNotIn('seed',s);self.assertNotIn('crash',s);r=self.raw(s['id'],'crash');r['starts']=time.time()-20;r['crash']=300;self.setraw(r);core.init();core.maintenance()
  s=social.read('crash',s['id']);self.assertEqual(s['players'][0]['payout'],200);self.assertEqual(self.xp('111'),10100);self.assertIn('seed',s)
  core.maintenance();self.assertEqual(self.xp('111'),10100)
 def test_crash_auto_tie_loses_and_manual_late_loses(self):
  s=self.crash();r=self.raw(s['id'],'crash');r['starts']=time.time()-20;r['crash']=200;self.setraw(r)
  out=self.op('111','crash/cashout',dict(round=s['id']));self.assertEqual(out['players'][0]['status'],'lost');self.assertEqual(self.xp('111'),9900)
 def test_manual_cashout_and_duplicate(self):
  s=self.crash(0);r=self.raw(s['id'],'crash');now=time.time();r['starts']=now-8;r['crash']=1000;self.setraw(r)
  with patch('social.time.time',return_value=now):r=self.op('111','crash/cashout',dict(round=s['id']))
  self.assertEqual(r['players'][0]['payout'],271);xp=self.xp('111');self.op('111','crash/cashout',dict(round=s['id']));self.assertEqual(self.xp('111'),xp)
 def test_crash_stale_button_does_not_join_new_round(self):
  s=self.crash();r=self.raw(s['id'],'crash');r['starts']=1;self.setraw(r);core.maintenance()
  with self.assertRaises(ValueError):self.op('222','crash/join',dict(round=s['id'],bet=100,auto=200))
  self.assertEqual(self.xp('222'),10000)
 def test_new_games_respect_disabled_setting(self):
  cfg={**social.DEFAULTS,'crashEnabled':False};self.op('111','settings',dict(social=cfg),True)
  with self.assertRaises(ValueError):self.crash()

if __name__=='__main__':unittest.main()

class DiscordPresentation(unittest.TestCase):
 def test_public_holdem_embed_contains_no_private_cards(self):
  import social_bot
  s=dict(id='table',kind='holdem',host='111',channel='1',buyin=1000,blind=20,status='lobby',created=0,lobby_end=60,revision=1,turn_seconds=45,players=[dict(uid='111',name='A',stack=1000),dict(uid='222',name='B',stack=1000)])
  poker.begin(s,0);p=poker.view(s);p['kind']='holdem';embed=social_bot.embed(p).to_dict()
  self.assertTrue(all(x['cards']==['🂠','🂠'] for x in p['players']))
  self.assertNotIn('deck',json.dumps(embed))
 def test_crash_commitment_matches_seed(self):
  import hashlib
  seed='a'*64;point=social.crash_point(seed)
  self.assertGreaterEqual(point,100);self.assertLessEqual(point,10000)
  s=dict(id='id',kind='crash',status='lobby',created=0,starts=time.time()+60,channel='',seed=seed,commitment=hashlib.sha256(seed.encode()).hexdigest(),crash=point,players=[],min_bet=10,max_bet=1000)
  self.assertNotIn('seed',social.public(s));s['status']='done';self.assertEqual(hashlib.sha256(social.public(s)['seed'].encode()).hexdigest(),social.public(s)['commitment'])
