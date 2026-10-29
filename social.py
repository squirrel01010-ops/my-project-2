"""Multiplayer casino transactions. Called inside core's immediate transaction."""
import hashlib
import json
import math
import secrets
import time
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
import poker

DEFAULTS=dict(holdemEnabled=True,holdemMinBuyin=100,holdemMaxBuyin=10000,holdemLobby=120,holdemTurn=45,
 lotteryEnabled=True,lotteryBasePrize=200000,lotteryPrice=100,lotteryHour=21,lotteryMaxTickets=20,lotteryFee=0,
 crashEnabled=True,crashLobby=20,crashMinBet=10,crashMaxBet=10000)
CATALOG={
 'holdem':dict(name='텍사스 홀덤',rules='2~6인 · 한 핸드 · 노리밋 · 사이드팟 지원 · 테이블 칩을 먼저 예치하고 종료 후 반환',symbol='♠'),
 'lottery':dict(name='서버 복권',rules='1~20에서 3개 선택 · 3개 일치 당첨권끼리 상금 분배 · 미당첨 상금 이월',symbol='🎟'),
 'crash':dict(name='크래시',rules='모집 후 배당 상승 · 종료 전에 정산 · 자동 정산 지원 · 종료 배당과 같으면 패배',symbol='🚀')}

def init(c):
 c.executescript('''CREATE TABLE IF NOT EXISTS live_games(id TEXT PRIMARY KEY,kind TEXT,state TEXT,status TEXT,created REAL,channel TEXT,message TEXT);
 CREATE TABLE IF NOT EXISTS lottery_tickets(id TEXT PRIMARY KEY,draw TEXT,uid TEXT,numbers TEXT,price INTEGER,payout INTEGER DEFAULT 0);
 CREATE INDEX IF NOT EXISTS live_status ON live_games(kind,status);
 CREATE INDEX IF NOT EXISTS ticket_draw_uid ON lottery_tickets(draw,uid);''')

def config(s):return {**DEFAULTS,**s.get('social',{})}
def validate(s):
 from core import integer
 if not isinstance(s,dict):raise ValueError('새 게임 설정 형식을 확인하세요')
 out={**DEFAULTS,**s}
 for k in ('holdemEnabled','lotteryEnabled','crashEnabled'):
  if type(out[k]) is not bool:raise ValueError('게임 활성화 설정을 확인하세요')
 for k in ('holdemMinBuyin','holdemMaxBuyin','lotteryPrice','crashMinBet','crashMaxBet'):integer(out[k],1,1000000)
 for low,high in [('holdemMinBuyin','holdemMaxBuyin'),('crashMinBet','crashMaxBet')]:
  if out[low]>out[high]:raise ValueError('게임 금액 범위를 확인하세요')
 integer(out['lotteryBasePrize'],0,1000000000)
 integer(out['holdemLobby'],15,600);integer(out['holdemTurn'],15,180);integer(out['lotteryHour'],0,23);integer(out['lotteryMaxTickets'],1,100);integer(out['lotteryFee'],0,30);integer(out['crashLobby'],10,120)
 return out

def save(c,s):
 c.execute('INSERT INTO live_games VALUES(?,?,?,?,?,?,NULL) ON CONFLICT(id) DO UPDATE SET state=excluded.state,status=excluded.status',
 (s['id'],s['kind'],json.dumps(s),s['status'],s['created'],s.get('channel','')))

def load(c,rid,kind):
 r=c.execute('SELECT state FROM live_games WHERE id=? AND kind=?',(str(rid),kind)).fetchone()
 if not r:raise ValueError('해당 판을 찾을 수 없습니다')
 return json.loads(r[0])

def public(s,viewer=None,now=None):
 if s['kind']=='holdem':return dict(kind='holdem',**poker.view(s,viewer))
 if s['kind']=='lottery':return {k:s[k] for k in ('id','kind','status','created','draw_at','price','base_prize','max_tickets','fee','pot','rollover','winning','winners','paid','channel') if k in s}
 out={k:s[k] for k in ('id','kind','status','created','starts','channel','commitment','max_bet','min_bet')}
 out['players']=[{k:p[k] for k in ('uid','name','bet','auto','status','payout','at') if k in p} for p in s['players']]
 out['multiplier']=min(s['crash']/100,multiplier(s,now or time.time())) if s['status']!='lobby' else 1
 if s['status']=='done':out.update(seed=s['seed'],crash=s['crash']/100)
 return out

def crash_point(seed):
 h=int(hashlib.sha256((seed+':crash').encode()).hexdigest()[:13],16)
 return max(100,min(10000,(99*2**52)//(2**52-h)))

def multiplier(s,now):return math.floor(math.exp(min(8,max(0,now-s['starts'])/8))*100)/100

def next_draw(s,now):
 dt=datetime.fromtimestamp(now,ZoneInfo(s['timezone']));target=dt.replace(hour=config(s)['lotteryHour'],minute=0,second=0,microsecond=0)
 if target.timestamp()<=now:target+=timedelta(days=1)
 return target.timestamp()

def ensure_draw(c,s,now):
 r=c.execute("SELECT state FROM live_games WHERE kind='lottery' AND status='open' LIMIT 1").fetchone()
 if r:
  current=json.loads(r[0])
  if 'base_prize' not in current:
   current['base_prize']=config(s)['lotteryBasePrize'];save(c,current)
  return current
 cfg=config(s)
 if not cfg['lotteryEnabled']:return None
 prev=c.execute("SELECT state FROM live_games WHERE kind='lottery' AND status='done' ORDER BY created DESC LIMIT 1").fetchone();rollover=json.loads(prev[0]).get('carry',0) if prev else 0
 d=dict(id=secrets.token_hex(12),kind='lottery',status='open',created=now,draw_at=next_draw(s,now),price=cfg['lotteryPrice'],base_prize=cfg['lotteryBasePrize'],max_tickets=cfg['lotteryMaxTickets'],fee=cfg['lotteryFee'],pot=0,rollover=rollover,channel=s['rankingChannel'])
 save(c,d);return d

def draw(c,s,now):
 from core import adjust,job
 winning=sorted(secrets.SystemRandom().sample(range(1,21),3));tickets=c.execute('SELECT * FROM lottery_tickets WHERE draw=? ORDER BY id',(s['id'],)).fetchall()
 winners=[t for t in tickets if json.loads(t['numbers'])==winning];pool=s.get('base_prize',200000)+s['rollover']+s['pot']-s['pot']*s['fee']//100
 s.update(winning=winning,winners=[],paid=0,carry=pool,status='done')
 if winners:
  share,odd=divmod(pool,len(winners))
  for i,t in enumerate(winners):
   payout=share+(i<odd)
   if payout:adjust(c,t['uid'],payout,'복권 당첨')
   c.execute('UPDATE lottery_tickets SET payout=? WHERE id=?',(payout,t['id']));s['winners'].append(dict(uid=t['uid'],ticket=t['id'],payout=payout));s['paid']+=payout
  s['carry']=0
 save(c,s);job(c,'social_result',dict(kind='lottery',id=s['id'],channel=s['channel']))

def poker_finish(c,s):
 from core import adjust
 if s.get('settled'):return
 for uid,amount in s['payouts'].items():
  if amount:adjust(c,uid,amount,'홀덤 테이블 반환')
 s['settled']=True

def cancel_table(c,s):
 s.update(status='cancelled',payouts={p['uid']:p['stack'] for p in s['players']},message='모집 취소 · 전액 반환');poker_finish(c,s)

def crash_pay(c,s,p,cents):
 from core import adjust
 amount=p['bet']*cents//100;p.update(status='cashed',payout=amount,at=cents/100)
 if amount:adjust(c,p['uid'],amount,'크래시 정산')

def tick(c,s,now):
 if s['kind']=='lottery':
  if s['status']=='open' and now>=s['draw_at']:draw(c,s,now)
 elif s['kind']=='crash':
  if s['status']=='lobby' and now>=s['starts']:s['status']='flying'
  if s['status']=='flying':
   reached=round(multiplier(s,now)*100)
   for p in s['players']:
    if p['status']=='bet' and p['auto'] and p['auto']<s['crash'] and reached>=p['auto']:crash_pay(c,s,p,p['auto'])
   if reached>=s['crash']:
    s['status']='done'
    for p in s['players']:
     if p['status']=='bet':p.update(status='lost',payout=0)
 elif s['kind']=='holdem':
  if s['status']=='lobby' and now>=s['lobby_end']:
   if len(s['players'])<2:cancel_table(c,s)
   else:poker.begin(s,now);s['revision']+=1
  elif s['status']=='active' and now>=s['deadline']:
   p=s['players'][s['turn']];action='check' if p['round']==s['bet'] else 'fold'
   # One expired turn per tick; reconnect never consumes everybody's turns at once.
   poker.act(s,p['uid'],action,None,s['deadline']-.001)
   if s['status']=='active':s['deadline']=now+s['turn_seconds']
   s['revision']+=1
  if s['status']=='done':poker_finish(c,s)
 save(c,s)

def maintenance(c,s,now):
 for row in c.execute("SELECT state FROM live_games WHERE status IN ('lobby','active','open','flying')").fetchall():tick(c,json.loads(row[0]),now)
 ensure_draw(c,s,now)

def lobby_allowed(s,kind,ctx,admin):
 cfg=config(s)
 if not s['casino'] or not cfg[kind+'Enabled']:raise ValueError('이 게임은 비활성화되어 있습니다')
 if not admin:
  if s['casinoChannels'] and ctx.get('channel') not in s['casinoChannels']:raise PermissionError('지정된 디스코드 채널에서 참여하세요')
  if s['casinoRoles'] and not set(ctx.get('roles',[]))&set(s['casinoRoles']):raise PermissionError('게임 참여 역할이 필요합니다')

def operate(c,actor,path,b,admin,ctx):
 from core import settings,ensure,adjust,integer,user
 now=time.time();cfgs=settings(c);cfg=config(cfgs);kind,action=path.split('/',1)
 # No admin impersonation: even administrators cannot play another person's hand.
 ensure(c,actor,ctx.get('name'));s=None
 if action in ('create','join','buy'):lobby_allowed(cfgs,kind,ctx,admin)
 if kind=='holdem':
  def vacant():
   for row in c.execute("SELECT state FROM live_games WHERE kind='holdem' AND status IN ('lobby','active')"):
    other=json.loads(row[0])
    if any(p['uid']==actor for p in other['players']):raise ValueError('이미 참여 중인 홀덤 테이블이 있습니다')
  if action=='create':
   vacant();buyin=integer(b.get('buyin'),cfg['holdemMinBuyin'],cfg['holdemMaxBuyin']);blind=integer(b.get('blind'),2,max(2,buyin//10))
   if blind*10>buyin:raise ValueError('바이인은 빅블라인드의 10배 이상이어야 합니다')
   s=dict(id=secrets.token_hex(12),kind='holdem',host=actor,channel=ctx.get('channel',''),status='lobby',created=now,lobby_end=now+cfg['holdemLobby'],buyin=buyin,blind=blind,turn_seconds=cfg['holdemTurn'],revision=0,players=[])
  else:
   s=load(c,b.get('table'),kind)
   old_revision=s['revision']
   tick(c,s,now)
   if action=='action' and s['revision']!=old_revision:return public(s,actor,now)
  if action in ('create','join'):
   if action=='join':vacant()
   if s['status']!='lobby' or len(s['players'])>=6:raise ValueError('모집 중인 빈자리가 없습니다')
   adjust(c,actor,-s['buyin'],'홀덤 바이인 예치');s['players'].append(dict(uid=actor,name=user(c,actor)['name'],stack=s['buyin']))
  elif action=='start':
   if s['host']!=actor:raise PermissionError('방장만 시작할 수 있습니다')
   if s['status']!='lobby' or len(s['players'])<2:raise ValueError('2명 이상 모여야 시작할 수 있습니다')
   poker.begin(s,now)
  elif action=='cancel':
   if s['host']!=actor:raise PermissionError('방장만 취소할 수 있습니다')
   if s['status']!='lobby':raise ValueError('시작한 판은 취소할 수 없습니다')
   cancel_table(c,s)
  elif action=='leave':
   if s['status']!='lobby':raise ValueError('시작 후에는 자기 차례에 폴드하세요')
   if s['host']==actor:cancel_table(c,s)
   else:
    p=next((p for p in s['players'] if p['uid']==actor),None)
    if not p:raise ValueError('테이블 참가자가 아닙니다')
    adjust(c,actor,p['stack'],'홀덤 모집 퇴장 반환');s['players'].remove(p)
  elif action=='action':
   if s['status']!='active':return public(s,actor,now)
   if b.get('revision')!=s['revision']:raise ValueError('테이블이 갱신되었습니다. 새로고침하세요')
   poker.act(s,actor,b.get('action'),b.get('amount'),now)
  else:raise ValueError('잘못된 홀덤 요청')
  s['revision']+=1
  if s['status']=='done':poker_finish(c,s)
 elif kind=='lottery':
  if action!='buy':raise ValueError('잘못된 복권 요청')
  s=load(c,b.get('draw'),kind)
  if s['status']!='open' or now>=s['draw_at']:raise ValueError('판매가 마감되었습니다. 새 추첨을 확인하세요')
  numbers=b.get('numbers');count=integer(b.get('count',1),1,s['max_tickets'])
  if numbers is not None and (not isinstance(numbers,list) or len(numbers)!=3 or any(type(x) is not int or not 1<=x<=20 for x in numbers) or len(set(numbers))!=3):raise ValueError('1~20에서 서로 다른 숫자 3개를 선택하세요')
  bought=c.execute('SELECT COUNT(*) FROM lottery_tickets WHERE draw=? AND uid=?',(s['id'],actor)).fetchone()[0]
  if bought+count>s['max_tickets']:raise ValueError('이번 회차 구매 한도를 초과합니다')
  adjust(c,actor,-s['price']*count,'복권 구매');tickets=[]
  for _ in range(count):
   nums=sorted(numbers if numbers is not None else secrets.SystemRandom().sample(range(1,21),3));tid=secrets.token_hex(12)
   c.execute('INSERT INTO lottery_tickets(id,draw,uid,numbers,price) VALUES(?,?,?,?,?)',(tid,s['id'],actor,json.dumps(nums),s['price']));tickets.append(dict(id=tid,numbers=nums))
  s['pot']+=s['price']*count;save(c,s);return dict(draw=public(s,actor,now),tickets=tickets)
 elif kind=='crash':
  if action=='join':
   channel=ctx.get('channel','');r=c.execute("SELECT state FROM live_games WHERE kind='crash' AND channel=? AND status IN ('lobby','flying') ORDER BY created DESC LIMIT 1",(channel,)).fetchone()
   if r:s=json.loads(r[0]);tick(c,s,now)
   if s is None or s['status']=='done':
    seed=secrets.token_hex(32);point=crash_point(seed)
    s=dict(id=secrets.token_hex(12),kind='crash',status='lobby',created=now,starts=now+cfg['crashLobby'],channel=channel,seed=seed,commitment=hashlib.sha256(seed.encode()).hexdigest(),crash=point,players=[],min_bet=max(cfg['crashMinBet'],cfgs['minBet']),max_bet=min(cfg['crashMaxBet'],cfgs['maxBet']))
   if b.get('round') and b['round']!=s['id']:raise ValueError('이 판은 이미 종료되었습니다. 새 회차에서 참여하세요')
   if s['status']!='lobby':raise ValueError('이미 출발했습니다. 다음 판에 참여하세요')
   if any(p['uid']==actor for p in s['players']):raise ValueError('이미 이 판에 베팅했습니다')
   if len(s['players'])>=100:raise ValueError('참가자가 가득 찼습니다')
   bet=integer(b.get('bet'),s['min_bet'],s['max_bet']);auto=integer(b.get('auto',0),0,9999)
   if auto and auto<101:raise ValueError('자동 정산은 1.01~99.99배입니다')
   adjust(c,actor,-bet,'크래시 베팅');s['players'].append(dict(uid=actor,name=user(c,actor)['name'],bet=bet,auto=auto,status='bet',payout=0))
  elif action=='cashout':
   s=load(c,b.get('round'),kind);tick(c,s,now);p=next((p for p in s['players'] if p['uid']==actor),None)
   if not p:raise PermissionError('본인 베팅만 정산할 수 있습니다')
   if s['status']=='lobby':raise ValueError('아직 출발 전입니다')
   if p['status']=='bet':crash_pay(c,s,p,round(multiplier(s,now)*100))
  else:raise ValueError('잘못된 크래시 요청')
 else:raise ValueError('게임을 찾을 수 없습니다')
 save(c,s);return public(s,actor,now)

def snapshot(c,uid=None):
 rows=c.execute("SELECT state FROM live_games ORDER BY created DESC LIMIT 50").fetchall()
 result={kind:[] for kind in CATALOG}
 for r in rows:
  s=json.loads(r[0]);result[s['kind']].append(public(s,uid))
 result['tickets']=[dict(r,numbers=json.loads(r['numbers'])) for r in c.execute('SELECT * FROM lottery_tickets WHERE uid=? ORDER BY rowid DESC LIMIT 100',(uid,))]
 return result

def read(kind,rid=None,viewer=None):
 import core
 with core.db(True) as c:
  maintenance(c,core.settings(c),time.time())
  if rid:s=load(c,rid,kind)
  else:
   r=c.execute('SELECT state FROM live_games WHERE kind=? ORDER BY created DESC LIMIT 1',(kind,)).fetchone()
   if not r:return None
   s=json.loads(r[0])
  return public(s,viewer)

