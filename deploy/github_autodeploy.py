"""Hosting bridge: watch public main, preserve state, restart one bot instance."""
import json, os, shutil, signal, sqlite3, subprocess, sys, time
from pathlib import Path
from dotenv import load_dotenv
ROOT=Path(__file__).resolve().parent.parent
STATE=ROOT/'.hosting'
SOURCE=STATE/'source'
REPO='https://github.com/squirrel01010-ops/my-project-2.git'
FILES={'app.py','bot.py','core.py','games.py','game_motion.py','poker.py','social.py','social_bot.py','run.py','runtime_health.py','backup.py','requirements.txt','requirements.lock'}
stopping=False
child=None

def command(args,cwd=ROOT):
 return subprocess.run(args,cwd=cwd,check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=90).stdout.decode().strip()
def allowed(name):
 p=Path(name)
 return name in FILES or (p.parts and p.parts[0]=='public' and '..' not in p.parts)
def fetch():
 if not (SOURCE/'.git').exists():
  command(['git','clone','--depth','1','--branch','main',REPO,str(SOURCE)])
 else:
  command(['git','fetch','--depth','1','origin','main'],SOURCE)
  command(['git','reset','--hard','FETCH_HEAD'],SOURCE)
 sha=command(['git','rev-parse','HEAD'],SOURCE)
 files=[x for x in command(['git','ls-files'],SOURCE).splitlines() if allowed(x)]
 for name in files:
  p=SOURCE/name
  if p.is_symlink() or not p.is_file():raise ValueError('Unsupported source file')
  if name.endswith('.py'):compile(p.read_text(),name,'exec')
 if 'run.py' not in files:raise ValueError('Missing runtime entry')
 return sha,files

def stop_child():
 global child
 if child is not None and child.poll() is None:
  os.killpg(child.pid,signal.SIGTERM)
  try:child.wait(timeout=12)
  except subprocess.TimeoutExpired:
   os.killpg(child.pid,signal.SIGKILL);child.wait()
 child=None
def start_child():
 global child
 child=subprocess.Popen([sys.executable,str(ROOT/'run.py')],cwd=ROOT,start_new_session=True)
def deploy(sha,files):
 stop_child()
 dest=STATE/'backups'/str(time.time_ns());dest.mkdir(parents=True,mode=0o700)
 db=Path(os.getenv('DB_PATH','bot.db'))
 if not db.is_absolute():db=ROOT/db
 if db.exists():
  with sqlite3.connect(db) as a,sqlite3.connect(dest/'bot.db') as b:a.backup(b)
 previous=[n for n in FILES if (ROOT/n).is_file()]
 previous+=['public/'+str(p.relative_to(ROOT/'public')) for p in (ROOT/'public').rglob('*') if p.is_file()]
 for name in previous:
  target=dest/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/name,target)
 try:
  if (SOURCE/'requirements.txt').read_bytes()!=(ROOT/'requirements.txt').read_bytes():
   command([sys.executable,'-m','pip','install','--disable-pip-version-check','--prefix',str(ROOT/'.local'),'-r',str(SOURCE/'requirements.txt')])
  for name in files:
   target=ROOT/name;target.parent.mkdir(parents=True,exist_ok=True)
   tmp=target.with_name(target.name+'.deploy-tmp');shutil.copy2(SOURCE/name,tmp);os.replace(tmp,target)
  start_child()
  # Confirm web and fresh Discord heartbeat without exporting private state.
  for attempt in range(30):
   if child.poll() is not None:raise RuntimeError('New runtime exited')
   try:
    command([sys.executable,'-c',"from dotenv import load_dotenv;load_dotenv('.env');from runtime_health import check;check()"])
    break
   except Exception:time.sleep(2)
  else:raise RuntimeError('New runtime did not become healthy')
 except Exception:
  stop_child()
  for name in previous:shutil.copy2(dest/name,ROOT/name)
  start_child()
  raise
 (STATE/'deployed.json').write_text(json.dumps({'repo':REPO,'branch':'main','commit':sha,'updated':time.time(),'pollSeconds':15}))
 print('GitHub auto-deploy ready: main '+sha[:12],flush=True)
 # Keep recent private rollback copies within the free storage allowance.
 backups=sorted((STATE/'backups').iterdir(),key=lambda p:p.name)
 for old in backups[:-5]:shutil.rmtree(old)

def main():
 global stopping
 os.chdir(ROOT);STATE.mkdir(exist_ok=True);load_dotenv(ROOT/'.env')
 signal.signal(signal.SIGTERM,lambda *_:set_stop())
 signal.signal(signal.SIGINT,lambda *_:set_stop())
 current=json.loads((STATE/'deployed.json').read_text()).get('commit') if (STATE/'deployed.json').exists() else None
 failed=None
 try:
  while not stopping:
   try:
    sha,files=fetch()
    if sha!=current and sha!=failed:
     try:deploy(sha,files);current=sha
     except Exception as e:
      failed=sha;print('Deployment failed; previous source restored: '+type(e).__name__,flush=True)
   except Exception as e:print('GitHub check failed: '+type(e).__name__,flush=True)
   if child is None or child.poll() is not None:start_child()
   for _ in range(15):
    if stopping:break
    time.sleep(1)
 finally:stop_child()
def set_stop():
 global stopping
 stopping=True
if __name__=='__main__':main()
