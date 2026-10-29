"""HTTP dashboard, Discord OAuth and authenticated JSON API."""
import csv
import hashlib
import hmac
import io
import json
import os
import secrets
import threading
import time
import urllib.parse
import urllib.request
from http.cookies import SimpleCookie
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).with_name('.env'))
import core

ROOT=Path(__file__).resolve().parent
ORIGIN=os.getenv('PUBLIC_URL','http://127.0.0.1:8080').rstrip('/')
ADMIN_TOKEN=os.getenv('ADMIN_TOKEN','')
GUILD=os.getenv('DISCORD_GUILD_ID','')
CLIENT=os.getenv('DISCORD_CLIENT_ID','')
BOT_TOKEN=os.getenv('DISCORD_TOKEN','')
SECURE=ORIGIN.startswith('https://')

def digest(v):return hashlib.sha256(v.encode()).hexdigest()
def discord_api(path,token,method='GET',data=None,bearer=False):
 raw=urllib.parse.urlencode(data).encode() if data is not None else None
 headers={'User-Agent':'OrbitBot/1.0'}
 if token:headers['Authorization']=('Bearer ' if bearer else 'Bot ')+token
 if raw:headers['Content-Type']='application/x-www-form-urlencoded'
 req=urllib.request.Request('https://discord.com/api/v10/'+path,data=raw,headers=headers,method=method)
 with urllib.request.urlopen(req,timeout=10) as response:return json.load(response)

def membership(uid):
 if not BOT_TOKEN or not GUILD:raise PermissionError('디스코드 연결 설정이 필요합니다')
 member=discord_api(f'guilds/{GUILD}/members/{uid}',BOT_TOKEN)
 with core.db() as c:s=core.settings(c)
 guild=discord_api('guilds/'+GUILD,BOT_TOKEN)
 roles=set(member.get('roles',[]));guild_roles=discord_api('guilds/'+GUILD+'/roles',BOT_TOKEN)
 admin=(uid in os.getenv('ADMIN_USER_IDS','').split(',') or str(guild.get('owner_id'))==uid or any(str(r['id']) in roles and int(r.get('permissions',0)) & 8 for r in guild_roles))
 return member,admin

class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass  # Never log OAuth codes, cookies or authorization headers.
 def send(self,status,data,kind='application/json',headers=None):
  raw=data if isinstance(data,bytes) else json.dumps(data,ensure_ascii=False).encode()
  self.send_response(status)
  for k,v in (headers or {}).items():self.send_header(k,v)
  self.send_header('Content-Type',kind+'; charset=utf-8');self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store')
  self.send_header('X-Content-Type-Options','nosniff');self.send_header('X-Frame-Options','DENY');self.send_header('Referrer-Policy','no-referrer')
  self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: https://cdn.discordapp.com; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
  self.end_headers();self.wfile.write(raw)
 def cookie(self,name):
  try:c=SimpleCookie(self.headers.get('Cookie',''));return c[name].value if name in c else ''
  except Exception:return ''
 def cookie_header(self,name,value,maxage):return f'{name}={value}; Path=/; HttpOnly; SameSite=Lax; Max-Age={maxage}'+('; Secure' if SECURE else '')
 def identity(self,csrf=False):
  auth=self.headers.get('Authorization','')
  if ADMIN_TOKEN and hmac.compare_digest(auth,'Bearer '+ADMIN_TOKEN):return dict(id='local-admin',name='로컬 관리자',admin=True,roles=[],local=True)
  token=self.cookie('orbit_session')
  with core.db() as c:r=c.execute('SELECT * FROM sessions WHERE hash=? AND expires>?',(digest(token),time.time())).fetchone()
  if not r:raise PermissionError('로그인이 필요합니다')
  if csrf and not hmac.compare_digest(self.headers.get('X-CSRF-Token',''),r['csrf']):raise PermissionError('잘못된 요청 인증입니다. 다시 로그인하세요')
  member,admin=membership(r['uid'])  # Recheck membership/roles on every request.
  return dict(id=r['uid'],name=r['name'],admin=admin,roles=member.get('roles',[]),csrf=r['csrf'],local=False)
 def do_GET(self):
  p=urllib.parse.urlparse(self.path);query=urllib.parse.parse_qs(p.query)
  try:
   if p.path in ('/','/app.js','/social.js','/style.css'):
    name={'/':'index.html','/app.js':'app.js','/social.js':'social.js','/style.css':'style.css'}[p.path];kind={'/':'text/html','/app.js':'application/javascript','/social.js':'application/javascript','/style.css':'text/css'}[p.path]
    return self.send(200,(ROOT/'public'/name).read_bytes(),kind)
   if p.path=='/health':return self.send(200,dict(ok=True,oauth=bool(CLIENT and GUILD and BOT_TOKEN and os.getenv('DISCORD_CLIENT_SECRET')),localLogin=bool(ADMIN_TOKEN)))
   if p.path=='/auth/login':
    if not CLIENT or not os.getenv('DISCORD_CLIENT_SECRET') or not GUILD or not BOT_TOKEN:raise ValueError('Discord OAuth 환경변수를 먼저 설정하세요')
    token=secrets.token_urlsafe(32)
    with core.db(True) as c:c.execute('INSERT INTO oauth_states VALUES(?,?)',(digest(token),time.time()+600))
    url='https://discord.com/oauth2/authorize?'+urllib.parse.urlencode(dict(client_id=CLIENT,redirect_uri=ORIGIN+'/auth/callback',response_type='code',scope='identify',state=token))
    return self.send(302,b'',headers={'Location':url,'Set-Cookie':self.cookie_header('orbit_oauth',token,600)})
   if p.path=='/auth/callback':
    state=query.get('state',[''])[0];cookie=self.cookie('orbit_oauth')
    if not state or not cookie or not hmac.compare_digest(state,cookie):raise PermissionError('로그인 요청이 일치하지 않습니다')
    with core.db(True) as c:
     valid=c.execute('SELECT 1 FROM oauth_states WHERE hash=? AND expires>?',(digest(state),time.time())).fetchone()
     if not valid:raise PermissionError('로그인 요청이 만료되었습니다')
     c.execute('DELETE FROM oauth_states WHERE hash=?',(digest(state),))
    code=query.get('code',[''])[0]
    if not code:raise ValueError('Discord 인증이 취소되었습니다')
    token=discord_api('oauth2/token','',method='POST',data=dict(client_id=CLIENT,client_secret=os.environ['DISCORD_CLIENT_SECRET'],grant_type='authorization_code',code=code,redirect_uri=ORIGIN+'/auth/callback'))
    me=discord_api('users/@me',token['access_token'],bearer=True);membership(me['id']);session=secrets.token_urlsafe(32)
    with core.db(True) as c:
     core.ensure(c,me['id'],me.get('global_name') or me['username']);c.execute('INSERT INTO sessions VALUES(?,?,?,?,?)',(digest(session),me['id'],me.get('global_name') or me['username'],secrets.token_urlsafe(24),time.time()+86400))
    return self.send(302,b'',headers={'Location':'/','Set-Cookie':self.cookie_header('orbit_session',session,86400)})
   who=self.identity()
   if p.path=='/api/state':return self.send(200,{**core.state(who['id'],who['admin']), 'identity':who})
   if p.path=='/api/export':
    if not who['admin']:raise PermissionError('관리자 권한이 필요합니다')
    stream=io.StringIO();writer=csv.writer(stream);writer.writerow(['id','uid','delta','reason','created'])
    with core.db() as c:
     for r in c.execute('SELECT * FROM ledger ORDER BY id'):
      writer.writerow(["'"+str(x) if isinstance(x,str) and x.startswith(('=','+','-','@','\t','\r')) else x for x in r])
    return self.send(200,stream.getvalue().encode('utf-8-sig'),'text/csv',{'Content-Disposition':'attachment; filename="orbit-ledger.csv"'})
   self.send(404,dict(error='페이지를 찾을 수 없습니다'))
  except PermissionError as e:self.send(403,dict(error=str(e)))
  except ValueError as e:self.send(400,dict(error=str(e)))
  except Exception:self.send(502,dict(error='서비스 연결에 실패했습니다. 봇 연결 및 설정을 확인하세요'))
 def do_POST(self):
  try:
   # No cross-origin mutations, including local token mode.
   origin=self.headers.get('Origin')
   if origin and origin!=ORIGIN:raise PermissionError('허용되지 않은 출처입니다')
   who=self.identity(csrf=True)
   n=int(self.headers.get('Content-Length',0))
   if not 0<n<=262144:raise ValueError('요청 크기를 확인하세요')
   body=json.loads(self.rfile.read(n))
   if not isinstance(body,dict):raise ValueError('JSON 객체를 입력하세요')
   if self.path=='/api/logout':
    with core.db(True) as c:c.execute('DELETE FROM sessions WHERE hash=?',(digest(self.cookie('orbit_session')),))
    return self.send(200,dict(ok=True),headers={'Set-Cookie':self.cookie_header('orbit_session','',0)})
   if not self.path.startswith('/api/'):return self.send(404,dict(error='잘못된 경로'))
   if self.path=='/api/gift':
    target=str(body.get('to',''))
    if not target.isdigit():raise ValueError('대상 유저 ID를 확인하세요')
    member,_=membership(target)
    if member.get('user',{}).get('bot'):raise ValueError('봇에게는 선물할 수 없습니다')
   result=core.operate(who['id'],self.path[5:],body,who['admin'],dict(name=who['name'],roles=who['roles']))
   self.send(200,result)
  except PermissionError as e:self.send(403,dict(error=str(e)))
  except (ValueError,TypeError,KeyError) as e:self.send(400,dict(error=str(e)))
  except Exception:self.send(500,dict(error='처리 중 오류가 발생했습니다. 중복 요청은 같은 요청 ID로 재시도하세요'))

def housekeeping():
 while True:
  try:
   core.maintenance()
   with core.db() as c:r=c.execute("SELECT value FROM meta WHERE key='last_backup'").fetchone()
   if not r or time.time()-float(r[0])>86400:
    from backup import create_backup
    create_backup()
  except Exception:print('유지보수 작업 실패: 데이터베이스와 디스크 상태를 확인하세요',flush=True)
  time.sleep(15)

def serve():
 threading.Thread(target=housekeeping,daemon=True).start()
 host=os.getenv('HOST','127.0.0.1');port=int(os.getenv('PORT','8080'))
 if host not in ('127.0.0.1','localhost') and not SECURE:raise RuntimeError('외부 접속은 HTTPS PUBLIC_URL 설정 후 사용하세요')
 print(f'ORBIT web: {ORIGIN}',flush=True);ThreadingHTTPServer((host,port),Handler).serve_forever()
if __name__=='__main__':serve()
