import concurrent.futures,json,tempfile,time,unittest
from unittest.mock import patch,AsyncMock
from types import SimpleNamespace
from datetime import date
import core,bot,games

class PlayFeatures(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.db=patch.object(core,'DB',self.tmp.name+'/play.db');self.db.start();core.init()
 def tearDown(self):self.db.stop();self.tmp.cleanup()
 def test_missions_progress_and_concurrent_claims_pay_once(self):
  for n in range(20):core.activity('a','A','chat','1',message_id=str(n))
  def claim(n):
   try:return core.operate('a','mission/claim',dict(kind='chat',key=str(n)))
   except ValueError:return None
  with concurrent.futures.ThreadPoolExecutor(4) as pool:results=list(pool.map(claim,range(4)))
  self.assertEqual(sum(x is not None for x in results),1)
  with core.db() as c:self.assertEqual(core.user(c,'a')['xp'],600)
  core.operate('a','attendance',dict(key='attendance'))
  self.assertTrue(next(m for m in core.missions('a')['missions'] if m['kind']=='attendance')['progress'])
  self.assertEqual(core.operate('a','mission/claim',dict(kind='attendance',key='attendance-mission'))['reward'],50)
 def test_weekly_settings_snapshot_and_settlement_once(self):
  with patch.object(core,'today',return_value=date(2026,10,26)):core.weekly_board()
  with core.db(True) as c:
   core.ensure(c,'a','A');c.execute("INSERT INTO activity VALUES('a','2026-10-27','1','chat',30,750)")
  core.operate('admin','settings',dict(weekly=dict(enabled=True,rewards=[999,0,0]),key='config'),True)
  with patch.object(core,'today',return_value=date(2026,11,2)):
   r=core.weekly_board();core.weekly_board()
  with core.db() as c:self.assertEqual(core.user(c,'a')['xp'],500)
  self.assertEqual(r['config']['rewards'][0],999)
  self.assertEqual(r['previous']['rankings']['chat'][0]['uid'],'a')
 def test_stats_fee_and_other_users_isolation(self):
  core.operate('a','adjust',dict(amount=1000,key='fund'),True)
  core.operate('a','settings',dict(probabilities={'dice':[1,0,0,0,0,0]},key='odds'),True)
  r=core.operate('a','play',dict(game='dice',choice=1,bet=100,key='play'))
  stats=core.game_stats('a')['games'][0]
  self.assertEqual((stats['plays'],stats['wins'],stats['net']),(1,1,500))
  self.assertFalse(core.game_stats('b')['games'])
  with core.db() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM game_results').fetchone()[0],1)
 def test_exact_preview_uses_fee_and_does_not_write(self):
  with core.db() as c:s=core.settings(c)
  s['probabilities']['dice']=[1,0,0,0,0,0];s['games']['dice']['fee']=10
  r=games.odds_preview(s,'dice','1',100)
  self.assertEqual((r['winChance'],r['returnRate'],r['expectedProfit']),(100,550,450))
  with core.db() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM game_rounds').fetchone()[0],0)
  for g in games.CATALOG:self.assertGreaterEqual(games.odds_preview(s,g,None)['returnRate'],0)
 def test_multiplayer_records_include_only_own_completed_results(self):
  with core.db(True) as c:
   for kind,state in [('holdem',dict(buyin=100,players=[dict(uid='a'),dict(uid='b')],payouts={'a':150,'b':50})),('crash',dict(players=[dict(uid='a',bet=100,payout=200)]))]:
    c.execute("INSERT INTO live_games(id,kind,state,status,created) VALUES(?,?,?,'done',?)",(kind,kind,json.dumps(state),time.time()))
   c.execute("INSERT INTO live_games(id,kind,state,status,created) VALUES('lottery','lottery','{}','done',?)",(time.time(),))
   c.execute("INSERT INTO lottery_tickets VALUES('ticket','lottery','a','[1,2,3]',10,100)")
  r=core.game_stats('a');self.assertEqual({g['game']:g['net'] for g in r['games']},{'holdem':50,'crash':100,'lottery':90})
  self.assertEqual(core.game_stats('b')['games'][0]['net'],-50)

class Replay(unittest.IsolatedAsyncioTestCase):
 async def test_replay_uses_saved_choice_and_checks_owner(self):
  with tempfile.TemporaryDirectory() as d,patch.object(core,'DB',d+'/bot.db'),patch.object(bot,'GUILD_ID',456):
   core.init();core.operate('123','adjust',dict(amount=1000,key='fund'),True)
   r=core.operate('123','play',dict(game='dice',choice=3,bet=100,key='game'),True)
   i=SimpleNamespace(type=bot.discord.InteractionType.component,guild_id=456,data={'custom_id':f"replay:{r['id']}:repeat"},user=SimpleNamespace(id=123),response=SimpleNamespace(is_done=lambda:False,send_message=AsyncMock()))
   with patch.object(bot,'start_game',new_callable=AsyncMock) as start:
    self.assertTrue(await bot.handle_replay(i));start.assert_awaited_once_with(i,'dice',100,3)
    i.user.id=999;start.reset_mock();await bot.handle_replay(i);start.assert_not_awaited();i.response.send_message.assert_awaited_once()
