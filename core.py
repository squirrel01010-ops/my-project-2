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
import social

ROOT=Path(__file__).resolve().parent
DB=os.getenv('DB_PATH',str(ROOT/'bot.db'))
DEFAULTS=dict(chatXP=25,cooldown=60,voiceXP=12,attendanceXP=50,streakBonus=10,streakCap=7,
 minBet=10,maxBet=10000,casino=True,gameCooldown=5,gameTimeout=900,levelBase=100,
 timezone='Asia/Seoul',excludedChannels=[],excludedRoles=[],casinoChannels=[],casinoRoles=[],adminRoles=[],
 voiceMinMembers=2,voiceAllowMuted=True,voiceAllowDeafened=False,dailyCap=5000,
 roleRewards=[],roleMode='highest',nicknameFormat='',levelChannel='',logChannel='',rankingChannel='',rankingInterval=3600,
 levelMessage='{user}님이 레벨 {level}에 도달했어요!',attendanceMessage='{user}님 출석 완료! +{xp} EXP · {streak}일 연속',
 embedColor='#9d85ff',boosts=[],seasonMode='off',seasonResetXP=False,seasonRewards=[],giftFee=0,
 social=social.DEFAULTS,
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
  CREATE TABLE IF NOT EXISTS game_rounds(id TEXT PRIMARY KEY,uid TEXT,game TEXT,bet INTEGER,state TEXT,fee INTEGER,revision INTEGER DEFAULT 0,created REAL,expires REAL,status TEXT,payout INTEGER DEFAULT 0);
  CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY,name TEXT,price INTEGER,kind TEXT,role_id TEXT,duration INTEGER,stock INTEGER,active INTEGER DEFAULT 1);
  CREATE TABLE IF NOT EXISTS inventory(id INTEGER PRIMARY KEY,product_id INTEGER,code TEXT,order_id TEXT);
  CREATE TABLE IF NOT EXISTS orders(id TEXT PRIMARY KEY,uid TEXT,product_id INTEGER,name TEXT,kind TEXT,role_id TEXT,expires REAL,created REAL,status TEXT,code TEXT);
  CREATE TABLE IF NOT EXISTS seasons(id INTEGER PRIMARY KEY,name TEXT,starts REAL,ends REAL,status TEXT,snapshot TEXT);
  CREATE TABLE IF NOT EXISTS season_scores(season_id INTEGER,uid TEXT,score INTEGER DEFAULT 0,PRIMARY KEY(season_id,uid));
  CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT);
  CREATE TABLE IF NOT EXISTS jobs(id INTEGER PRIMARY KEY,kind TEXT,payload TEXT,status TEXT DEFAULT 'pending',created REAL,error TEXT DEFAULT '');
  CREATE TABLE IF NOT EXISTS sessions(hash TEXT PRIMARY KEY,uid TEXT,name TEXT,csrf TEXT,expires REAL);
  CREATE TABLE IF NOT EXISTS oauth_states(hash TEXT PRIMARY KEY,expires REAL);
  CREATE TABLE IF NOT EXISTS login_links(hash TEXT PRIMARY KEY,uid TEXT,name TEXT,expires REAL);
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
 return out

def integer(v,lo=0,hi=1000000):return games.number(v,lo,hi)
def ident(v):
 v=str(v).strip()
 if not v or len(v)>100:raise ValueError('유저 ID를 확인하세요')
 return v

def ensure(c,uid,name=None):
 uid=ident(uid);c.execute('INSERT OR IGNORE INTO users(id,name) VALUES(?,?)',(uid,(name or uid)[:80]))
 if name:c.execute('UPDATE users SET name=? WHERE id=?',(name[:80],uid))
 return uid

def level(xp,s):return math.isqrt(xp//s['levelBase'])
def user(c,uid):
 r=c.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone()
 if not r:raise ValueError('등록되지 않은 멤버입니다')
 u=dict(r);s=settings(c);u['level']=level(u['xp'],s);u['nextXP']=(u['level']+1)**2*s['levelBase'];return u

def audit(c,actor,action,detail):c.execute('INSERT INTO audit(actor,action,detail,created) VALUES(?,?,?,?)',(actor,action,json.dumps(detail,ensure_ascii=False),time.time()))
def job(c,kind,payload):c.execute('INSERT INTO jobs(kind,payload,created) VALUES(?,?,?)',(kind,json.dumps(payload),time.time()))
def adjust(c,uid,delta,reason,score=True):
 integer(delta,-10**12,10**12);before=user(c,uid);s=settings(c)
 if not c.execute('UPDATE users SET xp=xp+? WHERE id=? AND xp+? BETWEEN 0 AND 1000000000000000',(delta,uid,delta)).rowcount:raise ValueError('경험치가 부족하거나 잔액 한도를 초과합니다')
 c.execute('INSERT INTO ledger(uid,delta,reason) VALUES(?,?,?)',(uid,delta,reason[:200]))
 if score:
  season=c.execute("SELECT id FROM seasons WHERE status='active'").fetchone()
  if season:c.execute('INSERT INTO season_scores VALUES(?,?,?) ON CONFLICT(season_id,uid) DO UPDATE SET score=score+excluded.score',(season[0],uid,delta))
 after=user(c,uid)
 if before['level']!=after['level']:
  job(c,'roles',dict(uid=uid))
  if after['level']>before['level']:job(c,'level',dict(uid=uid,level=after['level']))
 return after

def today(s,stamp=None):return datetime.fromtimestamp(stamp or time.time(),ZoneInfo(s['timezone'])).date()
def issue_login_link(uid,name):
 token=secrets.token_urlsafe(32)
 with db(True) as c:
  c.execute('DELETE FROM login_links WHERE expires<? OR uid=?',(time.time(),str(uid)))
  c.execute('INSERT INTO login_links VALUES(?,?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),str(uid),name,time.time()+300))
 return token

def login_link_user(token):
 if not isinstance(token,str) or not 20<=len(token)<=100:raise PermissionError('로그인 링크가 올바르지 않습니다. Discord에서 /관리로 다시 열어주세요.')
 with db() as c:r=c.execute('SELECT * FROM login_links WHERE hash=? AND expires>?',(hashlib.sha256(token.encode()).hexdigest(),time.time())).fetchone()
 if not r:raise PermissionError('로그인 링크가 만료되었거나 이미 사용됐어요. Discord에서 /관리로 새 링크를 받아주세요.')
 return dict(r)

def redeem_login_link(token):
 session=secrets.token_urlsafe(32);csrf=secrets.token_urlsafe(24)
 with db(True) as c:
  r=c.execute('SELECT * FROM login_links WHERE hash=? AND expires>?',(hashlib.sha256(token.encode()).hexdigest(),time.time())).fetchone()
  if not r:raise PermissionError('이미 사용했거나 만료된 로그인 링크입니다. /관리로 다시 열어주세요.')
  ensure(c,r['uid'],r['name'])
  c.execute('DELETE FROM login_links WHERE hash=?',(r['hash'],))
  c.execute('INSERT INTO sessions VALUES(?,?,?,?,?)',(hashlib.sha256(session.encode()).hexdigest(),r['uid'],r['name'],csrf,time.time()+86400))
 return session

def cooldown(c,key,seconds,now=None):
 now=time.time() if now is None else now;r=c.execute('SELECT stamp FROM cooldowns WHERE key=?',(key,)).fetchone()
 if r and now-r[0]<seconds:raise ValueError(f'{math.ceil(seconds-(now-r[0]))}초 후 다시 시도하세요')
 c.execute('INSERT INTO cooldowns VALUES(?,?) ON CONFLICT(key) DO UPDATE SET stamp=excluded.stamp',(key,now))

def validate_settings(value):
 s={**DEFAULTS,**value}
 for key in ('chatXP','cooldown','voiceXP','attendanceXP','streakBonus','streakCap','minBet','maxBet','gameCooldown','gameTimeout','levelBase','voiceMinMembers','dailyCap','rankingInterval','giftFee'):
  label={'chatXP':'채팅 경험치','cooldown':'채팅 쿨타임','voiceXP':'음성 경험치','attendanceXP':'출석 보상','streakBonus':'연속 출석 보상','streakCap':'출석 보상 누적 일수','minBet':'전체 최소 베팅','maxBet':'전체 최대 베팅','gameCooldown':'게임 쿨타임','gameTimeout':'게임 제한 시간','levelBase':'레벨 기준값','voiceMinMembers':'음성 최소 인원','dailyCap':'일일 한도','rankingInterval':'순위 갱신 간격','giftFee':'선물 수수료'}[key]
  try:integer(s[key],0,1000000)
  except ValueError:raise ValueError(f'{label}: 0~1,000,000 사이 정수를 입력하세요') from None
 if not 1<=s['minBet']<=s['maxBet']:raise ValueError('전체 베팅 한도: 최소 베팅은 1 이상, 최대 베팅은 최소 베팅 이상이어야 합니다')
 if s['levelBase']<1:raise ValueError('레벨 기준값은 1 이상이어야 합니다')
 if s['voiceMinMembers']<1:raise ValueError('음성 최소 인원은 1 이상이어야 합니다')
 if s['gameTimeout']<60:raise ValueError('게임 제한 시간은 60초 이상이어야 합니다')
 if s['rankingInterval']<60:raise ValueError('순위 갱신 간격은 60초 이상이어야 합니다')
 if s['giftFee']>30:raise ValueError('선물 수수료는 0~30%여야 합니다')
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
  name=games.CATALOG[g][0]
  for key,label,lo,hi in [('fee','수수료',0,30),('minBet','최소 베팅',1,1000000),('maxBet','최대 베팅',1,1000000)]:
   try:integer(cfg.get(key),lo,hi)
   except ValueError:raise ValueError(f'{name} {label}: {lo:,}~{hi:,} 사이 정수를 입력하세요') from None
  if cfg['maxBet']<cfg['minBet']:raise ValueError(f'{name}: 최대 베팅은 최소 베팅 이상이어야 합니다')
  for key,lo,hi in [('winChance',0,100),('winMultiplier',0,1000),('profitScale',0,100)]:
   v=cfg.get(key)
   if v is not None and (type(v) not in (int,float) or not math.isfinite(v) or not lo<=v<=hi):raise ValueError(f"{name} { {'winChance':'당첨 확률','winMultiplier':'당첨 배당','profitScale':'승리 수익 배율'}[key]}: {lo}~{hi} 사이 숫자를 입력하세요")
  if g not in games.CONFIGURABLE_CHANCE and (cfg.get('winChance') is not None or cfg.get('winMultiplier') is not None):raise ValueError('이 게임은 승률 직접 설정을 지원하지 않습니다')
  if g=='wheel':
   for key,default,maximum in [('wheelWeights',[1]*8,1000000),('wheelMultipliers',[0,0,0,0,1,1,2,4],1000)]:
    v=cfg.get(key,default)
    if not isinstance(v,list) or len(v)!=8 or any(type(x) not in (int,float) or not math.isfinite(x) or not 0<=x<=maximum for x in v):raise ValueError('돌림판은 8개 칸의 확률 가중치와 배당을 입력하세요')
   if sum(cfg.get('wheelWeights',[1]*8))<=0:raise ValueError('돌림판 가중치 합은 0보다 커야 합니다')
 s['social']=social.validate(s.get('social',{}))
 return s

def activity(uid,name,kind,channel,roles=(),category='',stamp=None):
 now=stamp if stamp is not None else time.time()
 with db(True) as c:
  s=settings(c);uid=ensure(c,uid,name)
  if kind not in ('chat','voice'):raise ValueError('활동 종류 오류')
  if str(channel) in s['excludedChannels'] or str(category) in s['excludedChannels'] or set(roles)&set(s['excludedRoles']):return 0
  try:cooldown(c,kind+':'+uid,s['cooldown'] if kind=='chat' else 55,now)
  except ValueError:return 0
  day=str(today(s,now));base=s['chatXP'] if kind=='chat' else s['voiceXP'];xp=boosted(base,s,kind,str(channel),roles,now)
  used=c.execute('SELECT COALESCE(SUM(xp),0) FROM activity WHERE uid=? AND day=?',(uid,day)).fetchone()[0]
  if s['dailyCap']:xp=min(xp,max(0,s['dailyCap']-used))
  c.execute('INSERT INTO activity VALUES(?,?,?,?,1,?) ON CONFLICT(uid,day,channel,kind) DO UPDATE SET amount=amount+1,xp=xp+excluded.xp',(uid,day,str(channel),kind,xp))
  if xp:adjust(c,uid,xp,('채팅' if kind=='chat' else '음성')+' 활동')
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
 # Fee is on positive profit only; stake refunds are never taxed.
 mult=s['mult'];mult=1+(mult-1)*s.get('profitScale',1) if mult>1 else mult
 raw=int(r['bet']*mult);payout=raw-max(0,raw-r['bet'])*r['fee']//100
 if payout:adjust(c,r['uid'],payout,games.CATALOG[r['game']][0]+' 정산')
 c.execute("UPDATE game_rounds SET status='done',payout=?,state=? WHERE id=?",(payout,json.dumps(s),r['id']))

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
    ensure(c,uid,b.get('name'));amount=integer(b.get('amount'),-100000000,100000000)
    if b.get('mode','add')=='set':
     if amount<0:raise ValueError('설정할 포인트는 0 이상이어야 합니다')
     amount-=user(c,uid)['xp']
    elif b.get('mode','add')!='add':raise ValueError('잘못된 조정 방식입니다')
    reason=str(b.get('reason','관리자 조정'))[:200];result=adjust(c,uid,amount,reason);audit(c,actor,path,dict(uid=uid,amount=amount,reason=reason));job(c,'log',dict(text=f'관리자 {actor}: {uid} 경험치 {amount:+,} ({reason})'));return result
   if path=='attendance':
    ensure(c,uid,context.get('name') if uid==actor else None);day=today(s);row=c.execute('SELECT * FROM attendance WHERE uid=?',(uid,)).fetchone()
    if row and row['last_day']==str(day):raise ValueError('오늘은 이미 출석했어요')
    streak=row['streak']+1 if row and row['last_day']==str(day-timedelta(days=1)) else 1;count=(row['total'] if row else 0)+1
    xp=boosted(s['attendanceXP']+s['streakBonus']*min(streak-1,s['streakCap']),s,'attendance',context.get('channel',''),context.get('roles',[]))
    c.execute('INSERT INTO attendance VALUES(?,?,?,?) ON CONFLICT(uid) DO UPDATE SET last_day=excluded.last_day,streak=excluded.streak,total=excluded.total',(uid,str(day),streak,count));adjust(c,uid,xp,'일일 출석');job(c,'roles',dict(uid=uid));return dict(ok=True,xp=xp,streak=streak,total=count)
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
    bet=integer(b.get('bet'),max(s['minBet'],cfg['minBet']),min(s['maxBet'],cfg['maxBet']))
    if c.execute("SELECT 1 FROM game_rounds WHERE uid=? AND status='active'",(uid,)).fetchone():raise ValueError('진행 중인 게임을 먼저 마치세요')
    cooldown(c,'game:'+uid,s['gameCooldown']);st=games.start(g,b.get('choice'),cfg);adjust(c,uid,-bet,games.CATALOG[g][0]+' 베팅')
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
    role=str(b.get('role_id',''))
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
    c.executemany('INSERT INTO inventory(product_id,code) VALUES(?,?)',[(pid,x) for x in codes]);audit(c,actor,path,dict(product_id=pid,count=len(codes)));return dict(ok=True)
   if path=='buy':
    ensure(c,uid,context.get('name') if uid==actor else None);p=c.execute('SELECT * FROM products WHERE id=? AND active=1',(integer(b.get('product_id'),1),)).fetchone()
    if not p or p['stock']==0:raise ValueError('판매 중인 재고가 없습니다')
    item=c.execute('SELECT * FROM inventory WHERE product_id=? AND order_id IS NULL LIMIT 1',(p['id'],)).fetchone() if p['kind']=='code' else None
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

def state(uid=None,admin=False):
 maintenance()
 with db() as c:
  s=settings(c);us=[dict(x) for x in c.execute('SELECT * FROM users ORDER BY xp DESC,id LIMIT 1000')]
  for u in us:u['level']=level(u['xp'],s)
  where='' if admin else ' WHERE uid=?';params=() if admin else (uid,)
  rounds=[round_view(r) for r in c.execute('SELECT * FROM game_rounds'+where+' ORDER BY created DESC LIMIT 30',params)]
  orders=[dict(r) for r in c.execute('SELECT * FROM orders'+where+' ORDER BY created DESC LIMIT 100',params)]
  if admin:
   for order in orders:
    if order['uid']!=uid:order['code']=None  # Codes are disclosed only to the purchasing member.
  stats=[dict(r) for r in c.execute('SELECT day,channel,kind,SUM(amount) amount,SUM(xp) xp,COUNT(DISTINCT uid) members FROM activity WHERE day>=? GROUP BY day,channel,kind ORDER BY day',((today(s)-timedelta(days=30)).isoformat(),))]
  seasons=[dict(r) for r in c.execute('SELECT * FROM seasons ORDER BY id DESC LIMIT 24')]
  for season in seasons:
   season['snapshot']=json.loads(season['snapshot'] or '[]')
   if season['status']=='active':season['snapshot']=[dict(r) for r in c.execute('SELECT u.id,u.name,ss.score FROM season_scores ss JOIN users u ON ss.uid=u.id WHERE season_id=? ORDER BY score DESC,u.id LIMIT 100',(season['id'],))]
  rankings={
   'monthly':[dict(r) for r in c.execute("SELECT u.id,u.name,SUM(l.delta) score FROM ledger l JOIN users u ON l.uid=u.id WHERE l.created>=? GROUP BY u.id ORDER BY score DESC,u.id LIMIT 100",(datetime.combine(today(s).replace(day=1),datetime.min.time(),ZoneInfo(s['timezone'])).astimezone(ZoneInfo('UTC')).strftime('%Y-%m-%d %H:%M:%S'),))],
   'attendance':[dict(r) for r in c.execute('SELECT u.id,u.name,a.total score FROM attendance a JOIN users u ON a.uid=u.id ORDER BY a.total DESC,u.id LIMIT 100')],
   'streak':[dict(r) for r in c.execute('SELECT u.id,u.name,CASE WHEN a.last_day>=? THEN a.streak ELSE 0 END score FROM attendance a JOIN users u ON a.uid=u.id ORDER BY score DESC,u.id LIMIT 100',((today(s)-timedelta(days=1)).isoformat(),))]}
  products=[dict(r) for r in c.execute('SELECT p.*,(SELECT COUNT(*) FROM inventory i WHERE i.product_id=p.id AND i.order_id IS NULL) codes FROM products p'+('' if admin else ' WHERE active=1'))]
  heartbeat=c.execute("SELECT value FROM meta WHERE key='heartbeat'").fetchone();connected=bool(heartbeat and time.time()-float(heartbeat[0])<120)
  visible=s if admin else {k:s[k] for k in ('minBet','maxBet','casino','games','giftFee','levelBase','gameTimeout','timezone','embedColor','social')}
  last_backup=c.execute("SELECT value FROM meta WHERE key='last_backup'").fetchone()
  return dict(social=social.snapshot(c,uid),socialCatalog=social.CATALOG,lastBackup=float(last_backup[0]) if last_backup and admin else None,users=us,settings=visible,connected=connected,rounds=rounds,products=products,orders=orders,seasons=seasons,rankings=rankings,
   ledger=[dict(r) for r in c.execute('SELECT * FROM ledger'+where+' ORDER BY id DESC LIMIT 100',params)],stats=stats if admin else [],
   casinoStats=[dict(r) for r in c.execute("SELECT game,COUNT(*) plays,SUM(bet) wagered,SUM(payout) paid FROM game_rounds WHERE status='done' GROUP BY game")] if admin else [],
   audit=[dict(r) for r in c.execute('SELECT * FROM audit ORDER BY id DESC LIMIT 100')] if admin else [],
   jobs=[dict(r) for r in c.execute("SELECT id,kind,status,error,created FROM jobs WHERE status!='done' ORDER BY id DESC LIMIT 50")] if admin else [],
   catalog={k:dict(name=v[0],rules=v[1],interactive=v[2]) for k,v in games.CATALOG.items()},me=user(c,uid) if uid and c.execute('SELECT 1 FROM users WHERE id=?',(uid,)).fetchone() else None)

def maintenance():
 with db(True) as c:
  now=time.time()
  social.maintenance(c,settings(c),now)
  for r in c.execute("SELECT * FROM game_rounds WHERE status='active' AND expires<?",(now,)).fetchall():
   st=json.loads(r['state']);games.finish(st,0,'제한 시간 초과: 베팅금 소멸');settle(c,r,st)
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

