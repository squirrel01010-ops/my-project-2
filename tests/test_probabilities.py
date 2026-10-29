import collections,json,random,tempfile,unittest
from unittest.mock import patch
import core,games,poker,social
odds=games.outcome_odds

class ProbabilityRules(unittest.TestCase):
 def test_validation_for_all_games(self):
  self.assertEqual(set(odds.CATALOG),set(games.CATALOG)|set(social.CATALOG))
  for game,rule in odds.CATALOG.items():
   weights=[1]*len(rule['labels'])
   self.assertEqual(odds.validate({game:weights})[game],weights)
   for bad in [[0]*len(weights),weights[:-1],[float('nan')]*len(weights),[True]*len(weights)]:
    with self.subTest(game=game,bad=bad),self.assertRaises(ValueError):odds.validate({game:bad})
 def test_forced_outcomes(self):
  for game,n,index,choice,key in [('slots',5,4,None,'symbols'),('scratch',4,2,None,'symbols'),('coin',6,5,'even','roll'),('dice',6,3,4,'roll'),('roulette',37,0,'zero','roll'),('wheel',8,7,None,'segment'),('bomb',5,3,None,'hazards'),('tower',3,2,None,'hazards'),('indian',13,12,None,'player')]:
   with self.subTest(game=game):
    w=[0]*n;w[index]=1;s=games.start(game,choice,{'outcomeWeights':w});value=s[key]
    expected=index+1 if game in ('coin','dice','indian') else index
    self.assertTrue(all(x==expected for x in value) if isinstance(value,list) else value==expected)
  w=[1,1,1]+[0]*6;s=games.start('mines',config={'outcomeWeights':w});self.assertEqual(set(s['hazards']),{0,1,2})
 def test_cards_preserve_deck_and_horse_permutation(self):
  w=[1]*13;w[0]=50
  s=games.start('blackjack',config={'outcomeWeights':w})
  self.assertEqual(collections.Counter(s['deck']+s['player']+s['dealer']),collections.Counter(list(range(1,14))*24))
  table=dict(blind=10,players=[dict(uid=str(i),stack=1000) for i in range(6)],turn_seconds=30,outcomeWeights=w)
  poker.begin(table,0)
  cards=table['deck']+sum([p['cards'] for p in table['players']],[])
  self.assertEqual(sorted(cards),list(range(52)))
  self.assertEqual(sorted(games.start('horse',1,{'outcomeWeights':[1,2,3,4,5]})['order']),[1,2,3,4,5])
 def test_highlow_uses_actual_direction_probability(self):
  w=[1]*13;w[12]=13
  s=dict(game='highlow',done=False,card=12,step=0,mult=1,outcomeWeights=w)
  with patch.object(games.RNG,'choices',return_value=[13]):games.action(s,'higher')
  self.assertAlmostEqual(s['mult'],25/13)
 def test_bot_choices_use_only_remaining_options(self):
  w=[1,2,3];s=games.start('baskin',config={'outcomeWeights':w});s['count']=28
  with patch.object(games.RNG,'choices',return_value=[1]) as choice:
   games.action(s,'count',1);self.assertEqual(choice.call_args.kwargs['weights'],[1,2])
  w=list(range(1,10));s=games.start('ttt',config={'outcomeWeights':w})
  with patch.object(games.RNG,'choices',return_value=[4]) as choice:
   games.action(s,'pick',0);self.assertEqual(choice.call_args.kwargs['weights'],w[1:])
 def test_weighted_distribution_and_no_zero_outcomes(self):
  rng=random.Random(2026);counts=collections.Counter(odds.choose(rng,[0,1,2],[0,1,3]) for _ in range(12000))
  self.assertEqual(counts[0],0);self.assertTrue(.73<counts[2]/12000<.77)
 def test_crash_seed_and_weights_reproduce_outcome(self):
  for i,p in enumerate(odds.CRASH_POINTS):
   w=[0]*len(odds.CRASH_POINTS);w[i]=1
   self.assertEqual(social.crash_point('fixed-seed',w),p)

class ProbabilityTransactions(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.db=patch.object(core,'DB',self.tmp.name+'/test.db');self.db.start();core.init();self.serial=0
  self.op('adjust',id='a',amount=100000)
 def tearDown(self):self.db.stop();self.tmp.cleanup()
 def op(self,path,**body):
  self.serial+=1;return core.operate('a',path,dict(body,key=str(self.serial)),True)
 def test_saved_weights_used_and_round_snapshot_survives_change(self):
  self.op('settings',probabilities={'highlow':[1]*13,'slots':[0,0,0,0,1]},gameCooldown=0)
  r=self.op('play',game='slots',bet=100);self.assertEqual(r['state']['symbols'],[4,4,4]);self.assertEqual(r['payout'],4000)
  r=self.op('play',game='highlow',bet=100)
  self.op('settings',probabilities={'highlow':[2]*13})
  with core.db() as c:stored=json.loads(c.execute('SELECT state FROM game_rounds WHERE id=?',(r['id'],)).fetchone()[0])
  self.assertEqual(stored['outcomeWeights'],[1]*13)
  with self.assertRaises(PermissionError):core.operate('b','settings',dict(probabilities={'slots':[1]*5},key='denied'))
 def test_lottery_and_crash_snapshot(self):
  probs={'lottery':[1,1,1]+[0]*17,'crash':[0,0,1]+[0]*6,'holdem':[2]+[1]*12}
  self.op('settings',probabilities=probs)
  # Start a new draw; existing selling draws must retain their settings.
  with core.db(True) as c:
   c.execute("DELETE FROM live_games WHERE kind='lottery'")
   d=social.ensure_draw(c,core.settings(c),0)
   self.assertEqual(d['outcomeWeights'],probs['lottery'])
   social.draw(c,d,1);self.assertEqual(d['winning'],[1,2,3])
  table=self.op('holdem/create',buyin=1000,blind=20);self.assertEqual(table['outcomeWeights'],probs['holdem'])
  r=self.op('crash/join',bet=100,auto=150)
  self.op('settings',probabilities={'crash':[1]+[0]*8})
  with core.db(True) as c:
   s=social.load(c,r['id'],'crash');self.assertEqual(s['crash'],200)
   social.tick(c,s,s['starts']+100)
   self.assertEqual(s['players'][0]['payout'],150)
   self.assertEqual(social.crash_point(s['seed'],s['outcomeWeights']),s['crash'])
