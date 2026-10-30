"""Single-guild economy. All monetary operations use an immediate SQLite transaction."""
import calendar
import hashlib
import json
import math
import os
import secrets
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import games
from games import outcome_odds as odds
import social

ROOT=Path(__file__).resolve().parent
def database_path():
 path=Path(os.getenv('DB_PATH','bot.db')).expanduser()
 return str(path if path.is_absolute() else ROOT/path)

DB=database_path()
DEFAULTS=dict(chatXP=25,cooldown=0,voiceXP=12,attendanceXP=50,streakBonus=10,streakCap=7,
 minBet=10,maxBet=10000,casino=True,gameCooldown=5,gameTimeout=900,levelBase=100,
 timezone='Asia/Seoul',excludedChannels=[],excludedRoles=[],casinoChannels=[],casinoRoles=[],adminRoles=[],
 voiceMinMembers=2,voiceAllowMuted=True,voiceAllowDeafened=False,dailyCap=5000,
 roleRewards=[],roleMode='highest',nicknameFormat='',levelChannel='',logChannel='',rankingChannel='',rankingInterval=3600,
 levelMessage='{user}님이 레벨 {level}에 도달했어요!',attendanceMessage='{user}님 출석 완료! +{xp} 띵조코인 · {streak}일 연속',
 embedColor='#9d85ff',boosts=[],seasonMode='off',seasonResetXP=False,seasonRewards=[],giftFee=0,
 social=social.DEFAULTS,probabilities={},missions=dict(chatTarget=20,voiceTarget=10,chatReward=100,voiceReward=100,attendanceReward=50),weekly=dict(enabled=True,rewards=[500,300,100]),
 games={k:dict(enabled=True,fee=0,minBet=10,maxBet=10000) for k in games.CATALOG})

@contextmanager
def db(write=False):
 c=sqlite3.connect(DB,timeout=15);c.row_factory=sqlite3.Row;c.execute('PRAGMA foreign_keys=ON');c.execute('PRAGMA busy_timeout=15000')
 try:
  if write:c.execute('BEGIN IMMEDIATE')
  yield c
  c.commit()
 except BaseException:c.rollback();raise
 finally:c.close()

def init():
 Path(DB).parent.mkdir(parents=True,exist_ok=True)
 with db() as c:
  c.execute('PRAGMA journal_mode=WAL')
  c.executescript('''
  CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,name TEXT,xp INTEGER NOT NULL DEFAULT 0 CHECK(xp>=0));
  CREATE TABLE IF NOT EXISTS settings(id INTEGER PRIMARY KEY,data TEXT);
  CREATE TABLE IF NOT EXISTS ledger(id INTEGER PRIMARY KEY,uid TEXT,delta INTEGER,reason TEXT,created TEXT DEFAULT CURRENT_TIMESTAMP);
  CREATE TABLE IF NOT EXISTS ops(key TEXT PRIMARY KEY,fingerprint TEXT,result TEXT);
  CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,actor TEXT,action TEXT,detail TEXT,created REAL);
  CREATE TABLE IF NOT EXISTS activity(uid TEXT,day TEXT,channel TEXT,kind TEXT,amount INTEGER DEFAULT 0,xp INTEGER DEFAULT 0,PRIMARY KEY(uid,day,channel,kind));
  CREATE TABLE IF NOT EXISTS attendance(uid TEXT PRIMARY KEY,last_day TEXT,streak INTEGER,total INTEGER);
  CREATE TABLE IF NOT EXISTS cooldowns(key TEXT PRIMARY KEY,stamp REAL);
  CREATE TABLE IF NOT EXISTS chat_messages(id TEXT PRIMARY KEY,created REAL);
  CREATE TABLE IF NOT EXISTS game_rounds(id TEXT PRIMARY KEY,uid TEXT,game TEXT,bet INTEGER,state TEXT,fee INTEGER,revision INTEGER DEFAULT 0,created REAL,expires REAL,status TEXT,payout INTEGER DEFAULT 0);
  CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY,name TEXT,price INTEGER,kind TEXT,role_id TEXT,duration INTEGER,stock INTEGER,active INTEGER DEFAULT 1);
  CREATE TABLE IF NOT EXISTS inventory(id INTEGER PRIMARY KEY,product_id INTEGER,code TEXT,order_id TEXT);
  CREATE INDEX IF NOT EXISTS inventory_product_code ON inventory(product_id,code);
  CREATE TABLE IF NOT EXISTS orders(id TEXT PRIMARY KEY,uid TEXT,product_id INTEGER,name TEXT,kind TEXT,role_id TEXT,expires REAL,created REAL,status TEXT,code TEXT);
  CREATE TABLE IF NOT EXISTS seasons(id INTEGER PRIMARY KEY,name TEXT,starts REAL,ends REAL,status TEXT,snapshot TEXT);
  CREATE TABLE IF NOT EXISTS season_scores(season_id INTEGER,uid TEXT,score INTEGER DEFAULT 0,PRIMARY KEY(season_id,uid));
  CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT);
  CREATE TABLE IF NOT EXISTS jobs(id INTEGER PRIMARY KEY,kind TEXT,payload TEXT,status TEXT DEFAULT 'pending',created REAL,error TEXT DEFAULT '');
  CREATE TABLE IF NOT EXISTS sessions(hash TEXT PRIMARY KEY,uid TEXT,name TEXT,csrf TEXT,expires REAL);
  CREATE TABLE IF NOT EXISTS oauth_states(hash TEXT PRIMARY KEY,expires REAL);
  ''')
  c.execute('CREATE INDEX IF NOT EXISTS users_ranking ON users(xp DESC,id)')
  c.execute('CREATE INDEX IF NOT EXISTS jobs_pending ON jobs(status,id)')
  c.execute('CREATE INDEX IF NOT EXISTS jobs_coalesce ON jobs(kind,status,payload)')
  c.execute('CREATE INDEX IF NOT EXISTS ledger_user_recent ON ledger(uid,id DESC)')
  c.execute('CREATE INDEX IF NOT EXISTS rounds_user_status ON game_rounds(uid,status)')
  c.execute('CREATE TABLE IF NOT EXISTS chat_health(id INTEGER PRIMARY KEY,last_received REAL,last_paid REAL,processed INTEGER DEFAULT 0,duplicates INTEGER DEFAULT 0,failures INTEGER DEFAULT 0,last_error TEXT,last_failure REAL)')
  c.execute('INSERT OR IGNORE INTO chat_health(id) VALUES(1)')
  c.execute("CREATE TABLE IF NOT EXISTS chat_inbox(id TEXT PRIMARY KEY,payload TEXT,status TEXT DEFAULT 'pending',attempts INTEGER DEFAULT 0,next_retry REAL DEFAULT 0,last_error TEXT DEFAULT '',created REAL,updated REAL)")
  c.execute('CREATE INDEX IF NOT EXISTS chat_inbox_due ON chat_inbox(status,next_retry)')
  c.execute('CREATE INDEX IF NOT EXISTS ledger_date ON ledger(created)')
  c.executescript('''
  CREATE TABLE IF NOT EXISTS mission_claims(uid TEXT,day TEXT,kind TEXT,reward INTEGER,PRIMARY KEY(uid,day,kind));
  CREATE TABLE IF NOT EXISTS attendance_days(uid TEXT,day TEXT,PRIMARY KEY(uid,day));
  CREATE TABLE IF NOT EXISTS game_results(round TEXT PRIMARY KEY,uid TEXT,game TEXT,bet INTEGER,payout INTEGER,created REAL);
  CREATE INDEX IF NOT EXISTS game_results_user ON game_results(uid,created);
  CREATE INDEX IF NOT EXISTS game_results_date ON game_results(created);
  CREATE TABLE IF NOT EXISTS weekly_periods(day TEXT PRIMARY KEY,ends TEXT,config TEXT,status TEXT,snapshot TEXT);
  ''')
  social.init(c)
  c.execute('INSERT OR IGNORE INTO settings VALUES(1,?)',(json.dumps(DEFAULTS),))
  current=settings(c);c.execute('UPDATE settings SET data=? WHERE id=1',(json.dumps(current),))
  if not c.execute("SELECT 1 FROM seasons WHERE status='active'").fetchone():
   c.execute("INSERT INTO seasons(name,starts,ends,status) VALUES(?,?,?,'active')",('시즌 1',time.time(),None))

def settings(c):
 value=json.loads(c.execute('SELECT data FROM settings WHERE id=1').fetchone()[0]);out={**DEFAULTS,**value}
 out['games']={k:{**DEFAULTS['games'][k],**value.get('games',{}).get(k,{})} for k in games.CATALOG}
 out['social']=social.config(out)
 for key in ('attendanceMessage','levelMessage'):out[key]=out[key].replace('EXP','띵조코인').replace('경험치','띵조코인')
 return out

def integer(v,lo=0,hi=1000000):return games.number(v,lo,hi)

def wager(v,minimum,balance):
 if type(v) is not int or v<minimum:raise ValueError(f'{minimum:,} 이상 정수를 입력하세요')
 if v>balance:raise ValueError('베팅할 띵조코인이 부족해요')
 return v
def ident(v):
 v=str(v).strip()
 if not v or len(v)>100:raise ValueError('유저 ID를 확인하세요')
 return v

def ensure(c,uid,name=None):
 uid=ident(uid);c.execute('INSERT OR IGNORE INTO users(id,name) VALUES(?,?)',(uid,(name or uid)[:80]))
 if name:c.execute('UPDATE users SET name=? WHERE id=? AND name!=?',(name[:80],uid,name[:80]))
 return uid

def level(xp,s):return math.isqrt(xp//s['levelBase'])
def user(c,uid,s=None):
 r=c.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone()
 if not r:raise ValueError('등록되지 않은 멤버입니다')
 u=dict(r);s=settings(c) if s is None else s;u['level']=level(u['xp'],s);u['nextXP']=(u['level']+1)**2*s['levelBase'];return u

def audit(c,actor,action,detail):c.execute('INSERT INTO audit(actor,action,detail,created) VALUES(?,?,?,?)',(actor,action,json.dumps(detail,ensure_ascii=False),time.time()))
def job(c,kind,payload):
 encoded=json.dumps(payload,sort_keys=True)
 if kind in ('roles','all_roles') and c.execute("SELECT 1 FROM jobs WHERE kind=? AND status='pending' AND payload=? LIMIT 1",(kind,encoded)).fetchone():return
 c.execute('INSERT INTO jobs(kind,payload,created) VALUES(?,?,?)',(kind,encoded,time.time()))

def recover_jobs():
 with db(True) as c:c.execute("UPDATE jobs SET status='pending' WHERE status='processing'")
def adjust(c,uid,delta,reason,score=True,s=None):
 integer(delta,-10**15,10**15);s=settings(c) if s is None else s;before=user(c,uid,s)
 if not c.execute('UPDATE users SET xp=xp+? WHERE id=? AND xp+? BETWEEN 0 AND 1000000000000000',(delta,uid,delta)).rowcount:raise ValueError('띵조코인이 부족하거나 잔액 한도를 초과합니다')
 c.execute('INSERT INTO ledger(uid,delta,reason) VALUES(?,?,?)',(uid,delta,reason[:200]))
 if score:
  season=c.execute("SELECT id FROM seasons WHERE status='active'").fetchone()
  if season:c.execute('INSERT INTO season_scores VALUES(?,?,?) ON CONFLICT(season_id,uid) DO UPDATE SET score=score+excluded.score',(season[0],uid,delta))
 after=user(c,uid,s)
 if before['level']!=after['level']:
  job(c,'roles',dict(uid=uid))
  if after['level']>before['level']:job(c,'level',dict(uid=uid,level=after['level']))
 return after

def today(s,stamp=None):return datetime.fromtimestamp(stamp or time.time(),ZoneInfo(s['timezone'])).date()
def cooldown(c,key,seconds,now=None):
 now=time.time() if now is None else now;r=c.execute('SELECT stamp FROM cooldowns WHERE key=?',(key,)).fetchone()
 if r and now-r[0]<seconds:raise ValueError(f'{math.ceil(seconds-(now-r[0]))}초 후 다시 시도하세요')
 c.execute('INSERT INTO cooldowns VALUES(?,?) ON CONFLICT(key) DO UPDATE SET stamp=excluded.stamp',(key,now))

def validate_settings(value):
 s={**DEFAULTS,**value}
 for key in ('chatXP','cooldown','voiceXP','attendanceXP','streakBonus','streakCap','minBet','maxBet','gameCooldown','gameTimeout','levelBase','voiceMinMembers','dailyCap','rankingInterval','giftFee'):
  integer(s[key],0,1000000)
 if not 1<=s['minBet'] or s['levelBase']<1 or s['voiceMinMembers']<1 or s['gameTimeout']<60 or s['rankingInterval']<60 or s['giftFee']>30:raise ValueError('설정 범위를 확인하세요')
 for k in ('casino','voiceAllowMuted','voiceAllowDeafened','seasonResetXP'):
  if type(s[k]) is not bool:raise ValueError('켜기/끄기 값을 확인하세요')
 try:ZoneInfo(s['timezone'])
 except Exception:raise ValueError('올바른 시간대를 입력하세요 (예: Asia/Seoul)')
 for k in ('excludedChannels','excludedRoles','casinoChannels','casinoRoles','adminRoles'):
  if not isinstance(s[k],list) or len(s[k])>100 or any(not isinstance(x,str) or not x.isdigit() for x in s[k]):raise ValueError(k+'에는 Discord ID 목록을 입력하세요')
 if s['roleMode'] not in ('highest','stack') or s['seasonMode'] not in ('off','monthly','quarterly','yearly'):raise ValueError('운영 모드를 확인하세요')
 for k in ('nicknameFormat','levelChannel','logChannel','rankingChannel','levelMessage','attendanceMessage','embedColor'):
  if not isinstance(s[k],str) or len(s[k])>1000:raise ValueError('문구가 너무 길거나 형식이 잘못되었습니다')
 for k in ('levelChannel','logChannel','rankingChannel'):
  if s[k] and not s[k].isdigit():raise ValueError('채널 ID를 확인하세요')
 if len(s['nicknameFormat'])>24:raise ValueError('닉네임 형식은 24자 이하로 입력하세요')
 if len(s['embedColor'])!=7 or s['embedColor'][0]!='#':raise ValueError('색상은 #RRGGBB 형식입니다')
 try:int(s['embedColor'][1:],16)
 except ValueError:raise ValueError('색상을 확인하세요')
 for listkey in ('roleRewards','boosts','seasonRewards'):
  if not isinstance(s[listkey],list) or len(s[listkey])>100:raise ValueError('보상·이벤트 목록은 100개 이하입니다')
 for r in s['roleRewards']:
  if r.get('type') not in ('level','attendance','streak') or not str(r.get('role','')).isdigit():raise ValueError('역할 보상 형식을 확인하세요')
  integer(r.get('threshold'),1)
 for r in s['seasonRewards']:
  integer(r.get('rank'),1,100);integer(r.get('xp',0),0,100000000)
  if r.get('role') and not str(r['role']).isdigit():raise ValueError('시즌 역할 ID를 확인하세요')
 for b in s['boosts']:
  if b.get('kind') not in ('all','chat','voice','attendance'):raise ValueError('배율 적용 대상을 확인하세요')
  if type(b.get('multiplier')) not in (int,float) or not 0<b['multiplier']<=10:raise ValueError('배율은 0 초과 10 이하입니다')
  if type(b.get('ends',0)) not in (int,float) or not math.isfinite(b.get('ends',0)):raise ValueError('이벤트 종료 시간을 확인하세요')
  for k in ('role','channel'):
   if b.get(k) and not str(b[k]).isdigit():raise ValueError('배율 역할/채널 ID를 확인하세요')
 for g in games.CATALOG:
  cfg=s['games'].get(g)
  if not isinstance(cfg,dict) or type(cfg.get('enabled')) is not bool:raise ValueError('게임 설정을 확인하세요')
  integer(cfg.get('fee'),0,30);integer(cfg.get('minBet'),1);integer(cfg.get('maxBet'),1)
 for k in ('redMultiplier','blackMultiplier','zeroMultiplier'):
  v=s['games']['roulette'].get(k,36 if k=='zeroMultiplier' else 2)
  if type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=1000:raise ValueError('룰렛 배율은 0~1000 사이 숫자여야 합니다')
 wheel=s['games']['wheel'].get('wheelMultipliers',[0,0,0,0,1,1,2,4])
 if not isinstance(wheel,list) or len(wheel)!=8 or any(type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=1000 for v in wheel):raise ValueError('돌림판 배율은 0~1000 사이 숫자 8개를 입력하세요')
 for key,default in [('playerMultiplier',2),('bankerMultiplier',1.95),('tieMultiplier',9)]:
  v=s['games']['baccarat'].get(key,default)
  if type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=1000:raise ValueError('바카라 배율은 0~1000 사이 숫자입니다')
 slot=s['games']['slots'];pair=slot.get('pairMultiplier',0.5);triples=slot.get('tripleMultipliers',games.SLOT_TRIPLES)
 if not isinstance(triples,list) or len(triples)!=5:raise ValueError('슬롯 모양별 배율은 5개를 입력하세요')
 if any(type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=1000 for v in [pair,*triples]):raise ValueError('슬롯 배율은 0~1000 사이 숫자여야 합니다')
 for key in ('missions','weekly'):
  if not isinstance(s[key],dict):raise ValueError('미션·주간 설정을 확인하세요')
 s['missions']={**DEFAULTS['missions'],**s['missions']}
 for key,v in s['missions'].items():integer(v,1 if key.endswith('Target') else 0,1000000)
 s['weekly']={**DEFAULTS['weekly'],**s['weekly']}
 if type(s['weekly']['enabled']) is not bool or not isinstance(s['weekly']['rewards'],list) or len(s['weekly']['rewards'])!=3:raise ValueError('주간 순위 보상은 1~3위 금액을 입력하세요')
 for v in s['weekly']['rewards']:integer(v,0,1000000)
 s['probabilities']=odds.validate(s.get('probabilities',{}))
 s['social']=social.validate(s.get('social',{}))
 return s

def activity(uid,name,kind,channel,roles=(),category='',stamp=None,message_id=None,settings_snapshot=None):
 now=stamp if stamp is not None else time.time()
 with db(True) as c:
  s=settings(c) if settings_snapshot is None else settings_snapshot;uid=ensure(c,uid,name)
  if kind not in ('chat','voice'):raise ValueError('활동 종류 오류')
  if kind=='chat':
   c.execute('UPDATE chat_health SET last_received=? WHERE id=1',(time.time(),))
   if message_id is not None and not c.execute('INSERT OR IGNORE INTO chat_messages VALUES(?,?)',(str(message_id),now)).rowcount:
    c.execute('UPDATE chat_health SET duplicates=duplicates+1 WHERE id=1');return 0
  else:
   if str(channel) in s['excludedChannels'] or str(category) in s['excludedChannels'] or set(roles)&set(s['excludedRoles']):return 0
   try:cooldown(c,'voice:'+uid,55,now)
   except ValueError:return 0
  day=str(today(s,now));base=s['chatXP'] if kind=='chat' else s['voiceXP'];xp=boosted(base,s,kind,str(channel),roles,now)
  if kind=='voice' and s['dailyCap']:
   used=c.execute("SELECT COALESCE(SUM(xp),0) FROM activity WHERE uid=? AND day=? AND kind='voice'",(uid,day)).fetchone()[0]
   xp=min(xp,max(0,s['dailyCap']-used))
  c.execute('INSERT INTO activity VALUES(?,?,?,?,1,?) ON CONFLICT(uid,day,channel,kind) DO UPDATE SET amount=amount+1,xp=xp+excluded.xp',(uid,day,str(channel),kind,xp))
  if xp:adjust(c,uid,xp,('채팅' if kind=='chat' else '음성')+' 활동',s=s)
  if kind=='chat':c.execute('UPDATE chat_health SET processed=processed+1,last_paid=CASE WHEN ?>0 THEN ? ELSE last_paid END WHERE id=1',(xp,time.time()))
  return xp

def boosted(base,s,kind,channel='',roles=(),now=None):
 multiplier=1
 for b in s['boosts']:
  if b['kind'] not in ('all',kind) or (b.get('ends') and b['ends']<(now or time.time())):continue
  if b.get('channel') and b['channel']!=channel:continue
  if b.get('role') and b['role'] not in roles:continue
  multiplier*=b['multiplier']
 return min(1000000,int(base*min(multiplier,100)))

def idempotent(c,actor,key,payload,fn):
 key=ident(key);full=actor+':'+key;finger=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
 old=c.execute('SELECT * FROM ops WHERE key=?',(full,)).fetchone()
 if old:
  if old['fingerprint']!=finger:raise ValueError('같은 요청 ID를 다른 작업에 사용할 수 없습니다')
  return json.loads(old['result'])
 result=fn();c.execute('INSERT INTO ops VALUES(?,?,?)',(full,finger,json.dumps(result)));return result

def round_view(r):
 out=dict(r);out['state']=games.public_view(json.loads(r['state']));return out

def settle(c,r,s):
 if r['status']!='active':return
 # Fee is on positive profit only; stake refunds are never taxed.
 raw=int(r['bet']*s['mult']);payout=raw-max(0,raw-r['bet'])*r['fee']//100
 if payout:adjust(c,r['uid'],payout,games.CATALOG[r['game']][0]+' 정산')
 c.execute("UPDATE game_rounds SET status='done',payout=?,state=? WHERE id=?",(payout,json.dumps(s),r['id']))
 c.execute("INSERT OR IGNORE INTO game_results VALUES(?,?,?,?,?,?)",(r['id'],r['uid'],r['game'],r['bet'],payout,time.time()))

def finish_season(c,name=None):
 old=c.execute("SELECT * FROM seasons WHERE status='active'").fetchone();s=settings(c)
 snapshot=[dict(r) for r in c.execute('SELECT u.id,u.name,ss.score FROM season_scores ss JOIN users u ON u.id=ss.uid WHERE ss.season_id=? ORDER BY ss.score DESC,u.id LIMIT 1000',(old['id'],))]
 c.execute("UPDATE seasons SET status='closed',ends=?,snapshot=? WHERE id=?",(time.time(),json.dumps(snapshot),old['id']))
 if s['seasonResetXP']:
  for u in c.execute('SELECT id,xp FROM users WHERE xp>0').fetchall():adjust(c,u['id'],-u['xp'],'시즌 초기화',False)
 nxt=time.time();end=season_end(s,nxt)
 c.execute("INSERT INTO seasons(name,starts,ends,status) VALUES(?,?,?,'active')",(name or f"시즌 {old['id']+1}",nxt,end))
 # Retire previous seasonal roles; new rewards belong to the new active season.
 c.execute("UPDATE orders SET status='expired' WHERE kind='season' AND status='active'")
 for reward in s['seasonRewards']:
  if reward['rank']>len(snapshot):continue
  u=snapshot[reward['rank']-1]
  if reward.get('xp'):adjust(c,u['id'],reward['xp'],'시즌 보상',False)
  if reward.get('role'):
   c.execute("INSERT INTO orders(id,uid,name,kind,role_id,created,status) VALUES(?,?,?,'season',?,?,'active')",(secrets.token_hex(12),u['id'],'시즌 순위 보상',reward['role'],nxt))
 job(c,'all_roles',{});job(c,'season',dict(name=old['name'],ranking=snapshot[:10]));return dict(ok=True,ranking=snapshot)

def season_end(s,stamp):
 if s['seasonMode']=='off':return None
 dt=datetime.fromtimestamp(stamp,ZoneInfo(s['timezone']));m=dt.month
 month=m+1 if s['seasonMode']=='monthly' else ((m-1)//3+1)*3+1 if s['seasonMode']=='quarterly' else 13
 year=dt.year+(month>12);month=1 if month>12 else month
 return datetime(year,month,1,tzinfo=dt.tzinfo).timestamp()

def operate(actor,path,b,admin=False,context=None):
 context=context or {};actor=ident(actor)
 with db(True) as c:
  def work():
   s=settings(c)
   admin_paths={'settings','adjust','product','season/end','inventory','test-message','backup','job/retry'}
   if path in admin_paths and not admin:raise PermissionError('관리자 권한이 필요합니다')
   if path.startswith(('holdem/','lottery/','crash/')):return social.operate(c,actor,path,b,admin,context)
   uid=ident(b.get('id',actor)) if admin else actor
   if path=='settings':
    value={**s,**{k:v for k,v in b.items() if k in DEFAULTS}};value=validate_settings(value)
    previous=c.execute("SELECT value FROM meta WHERE key='managed_roles'").fetchone()
    managed=set(json.loads(previous[0])) if previous else set()
    managed|={str(r['role']) for r in s['roleRewards']}
    c.execute("INSERT INTO meta VALUES('managed_roles',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(json.dumps(sorted(managed)),))
    c.execute('UPDATE settings SET data=? WHERE id=1',(json.dumps(value),))
    if value['seasonMode']!=s['seasonMode'] or value['timezone']!=s['timezone']:c.execute("UPDATE seasons SET ends=? WHERE status='active'",(season_end(value,time.time()),))
    audit(c,actor,path,{k:v for k,v in value.items() if v!=s.get(k)});job(c,'all_roles',{});return dict(ok=True)
   if path=='adjust':
    ensure(c,uid,b.get('name'));amount=integer(b.get('amount'),-10**15,10**15)
    if b.get('mode','add')=='set':
     if amount<0:raise ValueError('설정할 띵조코인은 0 이상이어야 합니다')
     amount-=user(c,uid)['xp']
    elif b.get('mode','add')!='add':raise ValueError('잘못된 조정 방식입니다')
    reason=str(b.get('reason','관리자 조정'))[:200];result=adjust(c,uid,amount,reason);audit(c,actor,path,dict(uid=uid,amount=amount,reason=reason));job(c,'log',dict(text=f'관리자 {actor}: {uid} 띵조코인 {amount:+,} ({reason})'));return result
   if path=='mission/claim-all':
    ensure(c,actor,context.get('name'));info=mission_state(c,actor,s);reward=0;count=0
    for item in info['missions']:
     if item['claimed'] or item['progress']<item['target']:continue
     c.execute('INSERT INTO mission_claims VALUES(?,?,?,?)',(actor,info['day'],item['kind'],item['reward']));reward+=item['reward'];count+=1
    if reward:adjust(c,actor,reward,'일일 미션 일괄 수령',False)
    return dict(ok=True,reward=reward,count=count)
   if path=='mission/claim':
    ensure(c,actor,context.get('name'));kind=b.get('kind');info=mission_state(c,actor,s)
    item=next((m for m in info['missions'] if m['kind']==kind),None)
    if not item or item['progress']<item['target']:raise ValueError('아직 미션을 완료하지 않았어요')
    if item['claimed']:raise ValueError('이미 받은 미션 보상입니다')
    c.execute('INSERT INTO mission_claims VALUES(?,?,?,?)',(actor,info['day'],kind,item['reward']))
    adjust(c,actor,item['reward'],'일일 미션: '+kind,False);return dict(ok=True,reward=item['reward'])
   if path=='attendance':
    ensure(c,uid,context.get('name') if uid==actor else None);day=today(s);row=c.execute('SELECT * FROM attendance WHERE uid=?',(uid,)).fetchone()
    if row and row['last_day']>=str(day):raise ValueError('오늘은 이미 출석했어요. 서버 시간대를 변경했다면 마지막 출석일 다음 날부터 받을 수 있어요')
    streak=row['streak']+1 if row and row['last_day']==str(day-timedelta(days=1)) else 1;count=(row['total'] if row else 0)+1
    xp=boosted(s['attendanceXP']+s['streakBonus']*min(streak-1,s['streakCap']),s,'attendance',context.get('channel',''),context.get('roles',[]))
    c.execute('INSERT INTO attendance VALUES(?,?,?,?) ON CONFLICT(uid) DO UPDATE SET last_day=excluded.last_day,streak=excluded.streak,total=excluded.total',(uid,str(day),streak,count));c.execute('INSERT OR IGNORE INTO attendance_days VALUES(?,?)',(uid,str(day)));adjust(c,uid,xp,'일일 출석');job(c,'roles',dict(uid=uid));return dict(ok=True,xp=xp,streak=streak,total=count)
   if path=='gift':
    ensure(c,uid,context.get('name') if uid==actor else None);to=ident(b.get('to',''));ensure(c,to)
    if to==uid:raise ValueError('자신에게 선물할 수 없습니다')
    amount=integer(b.get('amount'),1,100000000);fee=math.ceil(amount*s['giftFee']/100)
    adjust(c,uid,-amount-fee,'선물 → '+to);adjust(c,to,amount,'선물 ← '+uid);return dict(ok=True,fee=fee)
   if path=='play':
    ensure(c,uid,context.get('name') if uid==actor else None);g=b.get('game');cfg=s['games'].get(g)
    if not s['casino'] or not cfg or not cfg['enabled']:raise ValueError('이 게임은 현재 비활성화되어 있어요')
    if not admin:
     if s['casinoRoles'] and not set(context.get('roles',[]))&set(s['casinoRoles']):raise PermissionError('게임 허용 역할이 필요합니다')
     # Browser play is disabled if a channel-only casino policy is configured.
     if s['casinoChannels'] and context.get('channel') not in s['casinoChannels']:raise PermissionError('지정된 디스코드 채널에서 플레이하세요')
    bet=wager(b.get('bet'),max(s['minBet'],cfg['minBet']),user(c,uid)['xp'])
    expire_rounds(c,time.time(),uid)
    if c.execute("SELECT 1 FROM game_rounds WHERE uid=? AND status='active'",(uid,)).fetchone():raise ValueError('진행 중인 게임을 먼저 마치세요. /이어하기로 다시 열 수 있어요')
    if user(c,uid)['xp']<bet:raise ValueError('베팅할 띵조코인이 부족해요. /출석 또는 채팅 활동으로 띵조코인을 모은 뒤 /정보에서 잔액을 확인하세요')
    cooldown(c,'game:'+uid,s['gameCooldown']);st=games.start(g,b.get('choice'),{**cfg,'outcomeWeights':s['probabilities'].get(g,[])});st['choice']=b.get('choice');adjust(c,uid,-bet,games.CATALOG[g][0]+' 베팅')
    rid=secrets.token_hex(12);now=time.time()
    c.execute("INSERT INTO game_rounds(id,uid,game,bet,state,fee,created,expires,status) VALUES(?,?,?,?,?,?,?,?,'active')",(rid,uid,g,bet,json.dumps(st),cfg['fee'],now,now+s['gameTimeout']))
    r=c.execute('SELECT * FROM game_rounds WHERE id=?',(rid,)).fetchone()
    if st['done']:settle(c,r,st)
    return round_view(c.execute('SELECT * FROM game_rounds WHERE id=?',(rid,)).fetchone())
   if path=='game/action':
    r=c.execute('SELECT * FROM game_rounds WHERE id=?',(str(b.get('round','')),)).fetchone()
    if not r or (r['uid']!=actor and not admin):raise PermissionError('본인 게임만 진행할 수 있습니다')
    if r['status']!='active':raise ValueError('종료된 게임입니다')
    if r['expires']<time.time():raise ValueError('게임 시간이 만료되었습니다')
    if b.get('revision')!=r['revision']:raise ValueError('게임 화면이 갱신되었습니다. 새로고침하세요')
    st=games.action(json.loads(r['state']),b.get('action'),b.get('value'))
    c.execute('UPDATE game_rounds SET state=?,revision=revision+1 WHERE id=?',(json.dumps(st),r['id']))
    if st['done']:settle(c,r,st)
    return round_view(c.execute('SELECT * FROM game_rounds WHERE id=?',(r['id'],)).fetchone())
   if path=='product':
    name=str(b.get('name','')).strip()[:100];kind=b.get('kind');price=integer(b.get('price'),1,100000000);stock=integer(b.get('stock',-1),-1,1000000);duration=integer(b.get('duration',0),0,31536000)
    if not name or kind not in ('role','code'):raise ValueError('상품 정보를 확인하세요')
    role=str(b.get('role_id','')) if kind=='role' else ''
    if kind=='role' and not role.isdigit():raise ValueError('역할 ID를 입력하세요')
    active=1 if b.get('active',True) else 0;pid=b.get('product_id')
    if pid:
     if not c.execute('UPDATE products SET name=?,price=?,kind=?,role_id=?,duration=?,stock=?,active=? WHERE id=?',(name,price,kind,role,duration,stock,active,integer(pid,1))).rowcount:raise ValueError('상품을 찾을 수 없습니다')
    else:pid=c.execute('INSERT INTO products(name,price,kind,role_id,duration,stock,active) VALUES(?,?,?,?,?,?,?)',(name,price,kind,role,duration,stock,active)).lastrowid
    audit(c,actor,path,dict(product_id=pid,name=name));return dict(ok=True,product_id=pid)
   if path=='inventory':
    pid=integer(b.get('product_id'),1);codes=b.get('codes')
    if not isinstance(codes,list) or not 1<=len(codes)<=1000 or any(not isinstance(x,str) or not 1<=len(x)<=1000 for x in codes):raise ValueError('코드는 1~1000개 입력하세요')
    if not c.execute("SELECT 1 FROM products WHERE id=? AND kind='code'",(pid,)).fetchone():raise ValueError('코드 상품이 아닙니다')
    if len(set(codes))!=len(codes) or any(c.execute('SELECT 1 FROM inventory WHERE product_id=? AND code=?',(pid,code)).fetchone() for code in codes):raise ValueError('같은 상품에 이미 등록되었거나 중복된 코드가 있습니다')
    c.executemany('INSERT INTO inventory(product_id,code) VALUES(?,?)',[(pid,x) for x in codes]);audit(c,actor,path,dict(product_id=pid,count=len(codes)));return dict(ok=True)
   if path=='buy':
    ensure(c,uid,context.get('name') if uid==actor else None);p=c.execute('SELECT * FROM products WHERE id=? AND active=1',(integer(b.get('product_id'),1),)).fetchone()
    if not p or p['stock']==0:raise ValueError('판매 중인 재고가 없습니다')
    item=c.execute('SELECT i.* FROM inventory i WHERE i.product_id=? AND i.order_id IS NULL AND NOT EXISTS (SELECT 1 FROM inventory used WHERE used.product_id=i.product_id AND used.code=i.code AND used.order_id IS NOT NULL) LIMIT 1',(p['id'],)).fetchone() if p['kind']=='code' else None
    if p['kind']=='code' and not item:raise ValueError('코드 재고가 없습니다')
    if p['kind']=='role' and c.execute("SELECT 1 FROM orders WHERE uid=? AND role_id=? AND status='active' AND (expires IS NULL OR expires>?)",(uid,p['role_id'],time.time())).fetchone():raise ValueError('이미 보유 중인 역할입니다')
    oid=secrets.token_hex(12);adjust(c,uid,-p['price'],'상점 구매: '+p['name']);now=time.time()
    c.execute("INSERT INTO orders VALUES(?,?,?,?,?,?,?,?,'active',?)",(oid,uid,p['id'],p['name'],p['kind'],p['role_id'],now+p['duration'] if p['duration'] else None,now,item['code'] if item else None))
    if item:c.execute('UPDATE inventory SET order_id=? WHERE id=?',(oid,item['id']))
    if p['stock']>0:c.execute('UPDATE products SET stock=stock-1 WHERE id=?',(p['id'],))
    job(c,'roles',dict(uid=uid));job(c,'purchase',dict(uid=uid,order=oid));return dict(ok=True,order=oid,code=item['code'] if item else None)
   if path=='season/end':
    if b.get('confirm')!='시즌 종료':raise ValueError('확인 문구로 시즌 종료를 입력하세요')
    audit(c,actor,path,{});return finish_season(c,str(b.get('name',''))[:100] or None)
   if path=='test-message':job(c,'test',dict(channel=str(b.get('channel') or s['levelChannel'])));return dict(ok=True)
   if path=='job/retry':
    jid=integer(b.get('job_id'),1);c.execute("UPDATE jobs SET status='pending',error='' WHERE id=? AND status='failed'",(jid,));audit(c,actor,path,dict(job=jid));return dict(ok=True)
   raise ValueError('알 수 없는 작업')
  return idempotent(c,actor,b.get('key',''),dict(path=path,body=b),work)

def leaderboard(limit=20):
 with db() as c:
  s=settings(c);rows=[dict(r) for r in c.execute('SELECT id,name,xp FROM users ORDER BY xp DESC,id LIMIT ?',(limit,))]
  for u in rows:u['level']=level(u['xp'],s)
  return dict(users=rows)

def state(uid=None,admin=False,section=None):
 if section in (None,'casino','shop','seasons'):maintenance()
 with db() as c:
  s=settings(c);us=[dict(x) for x in c.execute('SELECT * FROM users ORDER BY xp DESC,id LIMIT 1000')] if section in (None,'overview','members','casino','shop') else []
  for u in us:u['level']=level(u['xp'],s)
  where='' if admin else ' WHERE uid=?';params=() if admin else (uid,)
  rounds=[round_view(r) for r in c.execute('SELECT * FROM game_rounds'+where+' ORDER BY created DESC LIMIT 30',params)] if section in (None,'casino') else []
  orders=[dict(r) for r in c.execute('SELECT * FROM orders'+where+' ORDER BY created DESC LIMIT 100',params)] if section in (None,'shop') else []
  if admin:
   for order in orders:
    if order['uid']!=uid:order['code']=None  # Codes are disclosed only to the purchasing member.
  stats=[dict(r) for r in c.execute('SELECT day,channel,kind,SUM(amount) amount,SUM(xp) xp,COUNT(DISTINCT uid) members FROM activity WHERE day>=? GROUP BY day,channel,kind ORDER BY day',((today(s)-timedelta(days=30)).isoformat(),))] if section in (None,'overview') and admin else []
  seasons=[dict(r) for r in c.execute('SELECT * FROM seasons ORDER BY id DESC LIMIT 24')] if section in (None,'seasons','overview') else []
  for season in seasons:
   season['snapshot']=json.loads(season['snapshot'] or '[]')
   if season['status']=='active':season['snapshot']=[dict(r) for r in c.execute('SELECT u.id,u.name,ss.score FROM season_scores ss JOIN users u ON ss.uid=u.id WHERE season_id=? ORDER BY score DESC,u.id LIMIT 100',(season['id'],))]
  rankings={
   'monthly':[dict(r) for r in c.execute("SELECT u.id,u.name,SUM(l.delta) score FROM ledger l JOIN users u ON l.uid=u.id WHERE l.created>=? GROUP BY u.id ORDER BY score DESC,u.id LIMIT 100",(datetime.combine(today(s).replace(day=1),datetime.min.time(),ZoneInfo(s['timezone'])).astimezone(ZoneInfo('UTC')).strftime('%Y-%m-%d %H:%M:%S'),))],
   'attendance':[dict(r) for r in c.execute('SELECT u.id,u.name,a.total score FROM attendance a JOIN users u ON a.uid=u.id ORDER BY a.total DESC,u.id LIMIT 100')],
   'streak':[dict(r) for r in c.execute('SELECT u.id,u.name,CASE WHEN a.last_day>=? THEN a.streak ELSE 0 END score FROM attendance a JOIN users u ON a.uid=u.id ORDER BY score DESC,u.id LIMIT 100',((today(s)-timedelta(days=1)).isoformat(),))]} if section in (None,'members') else {}
  products=[dict(r) for r in c.execute('SELECT p.*,(SELECT COUNT(DISTINCT i.code) FROM inventory i WHERE i.product_id=p.id AND i.order_id IS NULL AND NOT EXISTS (SELECT 1 FROM inventory used WHERE used.product_id=i.product_id AND used.code=i.code AND used.order_id IS NOT NULL)) codes FROM products p'+('' if admin else ' WHERE active=1'))] if section in (None,'shop') else []
  heartbeat=c.execute("SELECT value FROM meta WHERE key='heartbeat'").fetchone();connected=bool(heartbeat and time.time()-float(heartbeat[0])<120)
  visible=s if admin else {k:s[k] for k in ('minBet','maxBet','casino','games','giftFee','levelBase','gameTimeout','timezone','embedColor','social','probabilities')}
  last_backup=c.execute("SELECT value FROM meta WHERE key='last_backup'").fetchone()
  return dict(oddsCatalog=odds.CATALOG,social=social.snapshot(c,uid) if section in (None,'social') else {k:[] for k in ('holdem','lottery','crash','tickets')},socialCatalog=social.CATALOG,lastBackup=float(last_backup[0]) if last_backup and admin else None,users=us,settings=visible,connected=connected,rounds=rounds,products=products,orders=orders,seasons=seasons,rankings=rankings,
   ledger=[dict(r) for r in c.execute('SELECT * FROM ledger'+where+' ORDER BY id DESC LIMIT 100',params)] if section in (None,'logs') else [],stats=stats if admin else [],
   casinoStats=[dict(r) for r in c.execute("SELECT game,COUNT(*) plays,SUM(bet) wagered,SUM(payout) paid FROM game_rounds WHERE status='done' GROUP BY game")] if admin and section in (None,'logs') else [],
   audit=[dict(r) for r in c.execute('SELECT * FROM audit ORDER BY id DESC LIMIT 100')] if admin and section in (None,'logs') else [],
   jobs=[dict(r) for r in c.execute("SELECT id,kind,status,error,created FROM jobs WHERE status!='done' ORDER BY id DESC LIMIT 50")] if admin and section in (None,'logs') else [],
   catalog={k:dict(name=v[0],rules=v[1],interactive=v[2]) for k,v in games.CATALOG.items()},me=user(c,uid) if uid and c.execute('SELECT 1 FROM users WHERE id=?',(uid,)).fetchone() else None)

def expire_rounds(c,now,uid=None):
 query="SELECT * FROM game_rounds WHERE status='active' AND expires<?"
 params=(now,)
 if uid is not None:query+=' AND uid=?';params+=(uid,)
 for r in c.execute(query,params).fetchall():
  st=json.loads(r['state']);games.finish(st,0,'제한 시간 초과: 베팅금 소멸');settle(c,r,st)

def maintenance():
 with db(True) as c:
  now=time.time()
  c.execute("DELETE FROM chat_inbox WHERE status='paid' AND updated<?",(now-604800,))
  weekly_tick(c,settings(c))
  social.maintenance(c,settings(c),now)
  expire_rounds(c,now)
  expired=c.execute("SELECT * FROM orders WHERE status='active' AND expires IS NOT NULL AND expires<?",(now,)).fetchall()
  for r in expired:c.execute("UPDATE orders SET status='expired' WHERE id=?",(r['id'],));job(c,'roles',dict(uid=r['uid']))
  season=c.execute("SELECT * FROM seasons WHERE status='active'").fetchone()
  if season and season['ends'] and season['ends']<=now:finish_season(c)
  c.execute('DELETE FROM sessions WHERE expires<?',(now,));c.execute('DELETE FROM oauth_states WHERE expires<?',(now,))

def desired_roles(uid):
 with db(True) as c:
  s=settings(c);u=user(c,uid);a=c.execute('SELECT * FROM attendance WHERE uid=?',(uid,)).fetchone();streak=a['streak'] if a and a['last_day']>=str(today(s)-timedelta(days=1)) else 0
  values=dict(level=u['level'],attendance=a['total'] if a else 0,streak=streak);eligible=[r for r in s['roleRewards'] if values[r['type']]>=r['threshold']]
  if s['roleMode']=='highest':eligible=[max([r for r in eligible if r['type']==t],key=lambda r:r['threshold']) for t in values if any(r['type']==t for r in eligible)]
  want={str(r['role']) for r in eligible};managed={str(r['role']) for r in s['roleRewards']}
  managed|={r[0] for r in c.execute("SELECT DISTINCT role_id FROM orders WHERE role_id!=''")}
  for r in c.execute("SELECT role_id FROM orders WHERE uid=? AND status='active' AND (expires IS NULL OR expires>?)",(uid,time.time())):want.add(r[0])
  previous=c.execute("SELECT value FROM meta WHERE key='managed_roles' ").fetchone()
  if previous:managed|=set(json.loads(previous[0]))
  c.execute("INSERT INTO meta VALUES('managed_roles',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(json.dumps(sorted(managed)),))
  return want,managed,u,s

init()

def chat_health():
 with db() as c:
  row=c.execute('SELECT * FROM chat_health WHERE id=1').fetchone()
  s=settings(c)
  pending=c.execute("SELECT COUNT(*) FROM chat_inbox WHERE status!='paid'").fetchone()[0]
  return dict(row or {},reward=s['chatXP'],pending=pending)

def chat_failure(error):
 with db(True) as c:c.execute("UPDATE chat_health SET failures=failures+1,last_error=?,last_failure=?,last_received=? WHERE id=1",(type(error).__name__,time.time(),time.time()))

def history(uid,admin=False,filters=None):
 f=filters or {};page=integer(int(f.get('page',1)),1,1000000);clauses=[];params=[]
 target=str(f.get('uid','')).strip() if admin else uid
 if target:clauses.append('uid=?');params.append(target)
 reason=str(f.get('reason','')).strip()[:200]
 if reason:clauses.append("instr(reason,?)>0");params.append(reason)
 with db() as c:
  s=settings(c)
  for key,op,extra in [('start','>=',0),('end','<',1)]:
   if f.get(key):
    day=datetime.strptime(f[key],'%Y-%m-%d')+timedelta(days=extra)
    boundary=day.replace(tzinfo=ZoneInfo(s['timezone'])).astimezone(ZoneInfo('UTC')).strftime('%Y-%m-%d %H:%M:%S')
    clauses.append('created'+op+'?');params.append(boundary)
  where=' WHERE '+' AND '.join(clauses) if clauses else ''
  total=c.execute('SELECT COUNT(*) FROM ledger'+where,params).fetchone()[0]
  rows=[dict(r) for r in c.execute('SELECT * FROM ledger'+where+' ORDER BY id DESC LIMIT 50 OFFSET ?',params+[(page-1)*50])]
  return dict(rows=rows,total=total,page=page,pages=max(1,(total+49)//50))

def personal_activity(uid):
 with db() as c:
  s=settings(c);day=today(s);week=day-timedelta(days=day.weekday())
  rows=[dict(r) for r in c.execute('SELECT day,kind,SUM(amount) amount,SUM(xp) xp FROM activity WHERE uid=? AND day>=? GROUP BY day,kind ORDER BY day DESC',(uid,str(day-timedelta(days=29))))]
  totals=dict(c.execute('SELECT COALESCE(SUM(CASE WHEN delta>0 THEN delta ELSE 0 END),0) earned,COALESCE(SUM(CASE WHEN delta<0 THEN -delta ELSE 0 END),0) spent FROM ledger WHERE uid=?',(uid,)).fetchone())
  reasons=[v[0]+suffix for v in games.CATALOG.values() for suffix in (' 베팅',' 정산')]+['홀덤 바이인 예치','홀덤 테이블 반환','홀덤 모집 퇴장 반환','크래시 베팅','크래시 정산','복권 구매','복권 당첨']
  net=c.execute('SELECT COALESCE(SUM(delta),0) FROM ledger WHERE uid=? AND reason IN ('+','.join('?' for _ in reasons)+')',[uid,*reasons]).fetchone()[0]
  u=c.execute('SELECT xp FROM users WHERE id=?',(uid,)).fetchone()
  attendance=c.execute('SELECT * FROM attendance WHERE uid=?',(uid,)).fetchone()
  return dict(days=rows,today=str(day),week=str(week),balance=u[0] if u else 0,gameNet=net,attendance=dict(attendance) if attendance else None,**totals)

def social_state(uid,kind):
 if kind not in social.CATALOG:raise ValueError('게임 종류를 확인하세요')
 with db(True) as c:
  s=settings(c);now=time.time()
  for row in c.execute("SELECT state FROM live_games WHERE kind=? AND status IN ('lobby','active','open','flying')",(kind,)).fetchall():social.tick(c,json.loads(row[0]),now)
  if kind=='lottery':social.ensure_draw(c,s,now)
  rows=c.execute('SELECT state FROM live_games WHERE kind=? ORDER BY created DESC LIMIT 20',(kind,)).fetchall()
  result={kind:[social.public(json.loads(r[0]),uid) for r in rows]}
  if kind=='lottery':result['tickets']=[dict(r,numbers=json.loads(r['numbers'])) for r in c.execute('SELECT * FROM lottery_tickets WHERE uid=? ORDER BY rowid DESC LIMIT 100',(uid,))]
  return dict(social=result,settings=dict(social=s['social'],timezone=s['timezone'],casino=s['casino']),serverTime=time.time())


def queue_chat(message_id,payload):
 now=time.time()
 with db(True) as c:
  settings_now=settings(c)
  payload={**payload,'reward_settings':{k:settings_now[k] for k in ('chatXP','boosts','timezone','levelBase')}}
  added=c.execute('INSERT OR IGNORE INTO chat_inbox(id,payload,created,updated) VALUES(?,?,?,?)',(str(message_id),json.dumps(payload),now,now)).rowcount
  c.execute('UPDATE chat_health SET last_received=?,duplicates=duplicates+? WHERE id=1',(now,0 if added else 1))
 return bool(added)

def deliver_chat(message_id):
 now=time.time()
 with db(True) as c:
  if not c.execute("UPDATE chat_inbox SET status='processing',attempts=attempts+1,next_retry=?,updated=? WHERE id=? AND ((status='pending' AND next_retry<=?) OR (status='processing' AND next_retry<=?))",(now+120,now,str(message_id),now,now)).rowcount:return False
  row=c.execute('SELECT * FROM chat_inbox WHERE id=?',(str(message_id),)).fetchone()
 try:
  p=json.loads(row['payload'])
  activity(p['uid'],p['name'],'chat',p['channel'],p['roles'],p['category'],stamp=p['stamp'],message_id=str(message_id),settings_snapshot=p.get('reward_settings'))
 except Exception as e:
  with db(True) as c:c.execute("UPDATE chat_inbox SET status='pending',next_retry=?,last_error=?,updated=? WHERE id=?",(time.time()+min(300,2**min(row['attempts'],8)),type(e).__name__,time.time(),str(message_id)))
  chat_failure(e);return False
 with db(True) as c:c.execute("UPDATE chat_inbox SET status='paid',payload='{}',last_error='',updated=? WHERE id=?",(time.time(),str(message_id)))
 return True

def recover_chat(limit=50):
 with db() as c:ids=[r[0] for r in c.execute("SELECT id FROM chat_inbox WHERE status IN ('pending','processing') AND next_retry<=? ORDER BY next_retry LIMIT ?",(time.time(),limit))]
 return sum(deliver_chat(mid) for mid in ids)

def resume_game(uid):
 with db(True) as c:
  expire_rounds(c,time.time(),uid)
  r=c.execute("SELECT * FROM game_rounds WHERE uid=? AND status='active' ORDER BY created DESC LIMIT 1",(uid,)).fetchone()
  return round_view(r) if r else None

def shop_catalog(uid,page=1):
 page=integer(page,1,100000);now=time.time()
 with db() as c:
  total=c.execute('SELECT COUNT(*) FROM products WHERE active=1').fetchone()[0]
  page=min(page,max(1,(total+9)//10))
  rows=[dict(r) for r in c.execute("SELECT p.*,(SELECT COUNT(DISTINCT code) FROM inventory i WHERE product_id=p.id AND order_id IS NULL AND NOT EXISTS (SELECT 1 FROM inventory used WHERE used.product_id=i.product_id AND used.code=i.code AND used.order_id IS NOT NULL)) codes,EXISTS(SELECT 1 FROM orders o WHERE o.uid=? AND o.role_id=p.role_id AND o.status='active' AND (o.expires IS NULL OR o.expires>?)) owned FROM products p WHERE active=1 ORDER BY id LIMIT 10 OFFSET ?",(uid,now,(page-1)*10))]
  return dict(products=rows,page=page,pages=max(1,(total+9)//10))


def mission_state(c,uid,s):
 day=str(today(s));cfg={**DEFAULTS['missions'],**s.get('missions',{})}
 counts={r['kind']:r['n'] for r in c.execute('SELECT kind,SUM(amount) n FROM activity WHERE uid=? AND day=? GROUP BY kind',(uid,day))}
 a=c.execute('SELECT last_day FROM attendance WHERE uid=?',(uid,)).fetchone()
 claimed={r[0] for r in c.execute('SELECT kind FROM mission_claims WHERE uid=? AND day=?',(uid,day))}
 return dict(day=day,missions=[dict(kind=k,name=name,progress=progress,target=target,reward=reward,claimed=k in claimed) for k,name,progress,target,reward in [('chat','💬 채팅 미션',counts.get('chat',0),cfg['chatTarget'],cfg['chatReward']),('voice','🎙️ 음성 활동 미션',counts.get('voice',0),cfg['voiceTarget'],cfg['voiceReward']),('attendance','📅 오늘 출석',int(bool(a and a[0]==day)),1,cfg['attendanceReward'])]])

def missions(uid):
 with db() as c:return mission_state(c,uid,settings(c))

def game_stats(uid):
 with db() as c:
  query="""SELECT id,game,bet,payout,created FROM game_rounds WHERE uid=? AND status='done'
  UNION ALL SELECT g.id,g.kind,CASE WHEN g.kind='holdem' THEN json_extract(g.state,'$.buyin') ELSE json_extract(p.value,'$.bet') END,
   CASE WHEN g.kind='holdem' THEN COALESCE(json_extract(g.state,?),0) ELSE COALESCE(json_extract(p.value,'$.payout'),0) END,g.created
   FROM live_games g,json_each(g.state,'$.players') p WHERE g.kind IN ('holdem','crash') AND g.status='done' AND json_extract(p.value,'$.uid')=?
  UNION ALL SELECT t.id,'lottery',t.price,t.payout,g.created FROM lottery_tickets t JOIN live_games g ON g.id=t.draw WHERE t.uid=? AND g.status='done'"""
  args=(uid,'$.payouts.'+json.dumps(str(uid)),uid,uid)
  rows=[dict(r) for r in c.execute("SELECT game,COUNT(*) plays,SUM(CASE WHEN payout>bet THEN 1 ELSE 0 END) wins,SUM(CASE WHEN payout=bet THEN 1 ELSE 0 END) draws,SUM(bet) wagered,SUM(payout) paid,SUM(payout-bet) net,MAX(payout) best FROM ("+query+") GROUP BY game",args)]
  recent=[dict(r) for r in c.execute('SELECT * FROM ('+query+') ORDER BY created DESC,id DESC LIMIT 20',args)]
  return dict(games=rows,recent=recent,scope='게임 19종 · 복권은 1장=1판 · 완료된 판만 집계 · 수수료 반영 · 승리는 반환액이 베팅액보다 큰 판')


def weekly_ranking(c,day,end,s,limit=20):
 start=datetime.fromisoformat(day).replace(tzinfo=ZoneInfo(s['timezone'])).timestamp();stop=datetime.fromisoformat(end).replace(tzinfo=ZoneInfo(s['timezone'])).timestamp()
 queries={
 'chat':("SELECT uid,SUM(amount) score FROM activity WHERE day>=? AND day<? AND kind='chat' GROUP BY uid HAVING score>0",(day,end)),
 'attendance':('SELECT uid,COUNT(*) score FROM attendance_days WHERE day>=? AND day<? GROUP BY uid',(day,end)),
 'games':('SELECT uid,SUM(payout-bet) score FROM game_results WHERE created>=? AND created<? GROUP BY uid HAVING score>0',(start,stop))}
 out={}
 for kind,(query,args) in queries.items():
  out[kind]=[dict(r) for r in c.execute('SELECT q.uid,u.name,q.score FROM ('+query+') q JOIN users u ON q.uid=u.id ORDER BY q.score DESC,q.uid LIMIT ?',(*args,limit))]
 return out

def weekly_tick(c,s):
 day=today(s);monday=day-timedelta(days=day.weekday());cfg={**DEFAULTS['weekly'],**s.get('weekly',{})}
 for row in c.execute("SELECT * FROM weekly_periods WHERE status='active' AND ends<=?",(str(day),)).fetchall():
  saved=json.loads(row['config']);ranking=weekly_ranking(c,row['day'],row['ends'],{'timezone':saved['timezone']})
  if saved['enabled']:
   for kind,rows in ranking.items():
    for i,u in enumerate(rows[:3]):
     reward=saved['rewards'][i]
     if reward:adjust(c,u['uid'],reward,'주간 '+kind+' '+str(i+1)+'위 보상',False)
  c.execute("UPDATE weekly_periods SET status='done',snapshot=? WHERE day=?",(json.dumps(ranking),row['day']))
 c.execute("INSERT OR IGNORE INTO weekly_periods VALUES(?,?,?,'active',NULL)",(str(monday),str(monday+timedelta(days=7)),json.dumps(dict(cfg,timezone=s['timezone']))))

def weekly_board():
 with db(True) as c:
  s=settings(c);weekly_tick(c,s)
  row=c.execute("SELECT * FROM weekly_periods WHERE status='active' ORDER BY day DESC LIMIT 1").fetchone();cfg=json.loads(row['config'])
  previous=c.execute("SELECT * FROM weekly_periods WHERE status='done' ORDER BY day DESC LIMIT 1").fetchone()
  return dict(day=row['day'],ends=row['ends'],config=cfg,rankings=weekly_ranking(c,row['day'],row['ends'],cfg),previous=dict(day=previous['day'],rankings=json.loads(previous['snapshot'])) if previous else None)


def insights(uid,admin=False,period='week',game=''):
 with db() as c:
  s=settings(c);day=today(s);start=day if period=='today' else day.replace(day=1) if period=='month' else day-timedelta(days=day.weekday());previous=start-(day-start+timedelta(days=1))
  utc=lambda d:datetime.combine(d,datetime.min.time(),ZoneInfo(s['timezone'])).astimezone(ZoneInfo('UTC')).strftime('%Y-%m-%d %H:%M:%S')
  reasons=[v[0]+suffix for k,v in games.CATALOG.items() if not game or k==game for suffix in (' 베팅',' 정산')]
  if not game:reasons+=['홀덤 바이인 예치','홀덤 테이블 반환','홀덤 모집 퇴장 반환','크래시 베팅','크래시 정산','복권 구매','복권 당첨']
  sql='SELECT delta,created FROM ledger WHERE uid=? AND created>=? AND reason IN ('+','.join('?' for _ in reasons)+')'
  rows=c.execute(sql,[uid,utc(previous),*reasons]).fetchall();daily={};old=0
  for r in rows:
   d=datetime.fromisoformat(r['created']).replace(tzinfo=ZoneInfo('UTC')).astimezone(ZoneInfo(s['timezone'])).date()
   if d<start:old+=r['delta']
   else:daily[str(d)]=daily.get(str(d),0)+r['delta']
  u=c.execute('SELECT xp FROM users WHERE id=?',(uid,)).fetchone();rank=1+c.execute('SELECT COUNT(*) FROM users WHERE xp>? OR (xp=? AND id<?)',(u[0],u[0],uid)).fetchone()[0] if u else None
  a=c.execute('SELECT * FROM attendance WHERE uid=?',(uid,)).fetchone()
  result=dict(start=str(start),end=str(day),daily=daily,net=sum(daily.values()),previous=old,rank=rank,attendance=dict(a) if a else None,missions=mission_state(c,uid,s))
  week=c.execute("SELECT * FROM weekly_periods WHERE status='active' ORDER BY day DESC LIMIT 1").fetchone()
  result['weeklySelf']={}
  if week:
   boards=weekly_ranking(c,week['day'],week['ends'],json.loads(week['config']),1000000)
   for kind,board in boards.items():
    position=next((i for i,x in enumerate(board) if x['uid']==uid),None)
    result['weeklySelf'][kind]=dict(rank=position+1,gap=board[position-1]['score']-board[position]['score'] if position else 0) if position is not None else None
  if admin:
   result['economy']=[dict(r) for r in c.execute("SELECT reason,SUM(CASE WHEN delta>0 THEN delta ELSE 0 END) incoming,SUM(CASE WHEN delta<0 THEN -delta ELSE 0 END) outgoing,COUNT(*) count FROM ledger WHERE created>=? GROUP BY reason ORDER BY count DESC",(utc(start),))]
   result['circulation']=c.execute('SELECT COALESCE(SUM(xp),0) FROM users').fetchone()[0]
   result['returns']=[dict(r) for r in c.execute("SELECT game,COUNT(*) samples,SUM(bet) bets,SUM(payout) payouts FROM game_rounds WHERE status='done' AND created>=? GROUP BY game",(datetime.fromisoformat(str(start)).replace(tzinfo=ZoneInfo(s['timezone'])).timestamp(),))]
  if admin:
   for row in result['returns']:
    row['expected']=games.odds_preview(s,row['game'],None,100)
  return result


def chat_diagnostic(uid,channel,roles=()):
 with db() as c:
  s=settings(c);h=dict(c.execute('SELECT * FROM chat_health WHERE id=1').fetchone())
  pending=c.execute("SELECT COUNT(*) FROM chat_inbox WHERE status!='paid' AND json_extract(payload,'$.uid')=?",(uid,)).fetchone()[0]
  error=c.execute("SELECT last_error FROM chat_inbox WHERE status!='paid' AND json_extract(payload,'$.uid')=? AND last_error!='' ORDER BY updated DESC LIMIT 1",(uid,)).fetchone()
  paid=c.execute("SELECT delta,created FROM ledger WHERE uid=? AND reason='채팅 활동' ORDER BY id DESC LIMIT 1",(uid,)).fetchone()
  count=c.execute("SELECT COALESCE(SUM(amount),0),COALESCE(SUM(xp),0) FROM activity WHERE uid=? AND channel=? AND kind='chat' AND day=?",(uid,channel,str(today(s)))).fetchone()
  return dict(base=s['chatXP'],expected=boosted(s['chatXP'],s,'chat',channel,roles),received=h['last_received'],pending=pending,error=error[0] if error else '',paid=dict(paid) if paid else None,messages=count[0],coins=count[1])
