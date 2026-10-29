"""One web+bot instance; exit on failure so the hosting platform can restart it."""
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from dotenv import load_dotenv
ROOT=Path(__file__).resolve().parent

def main():
 load_dotenv(ROOT/'.env')
 has_bot=bool(os.getenv('DISCORD_TOKEN') and os.getenv('DISCORD_GUILD_ID'))
 if os.getenv('REQUIRE_DISCORD')=='1' and not has_bot:raise SystemExit('DISCORD_TOKEN and DISCORD_GUILD_ID are required')
 if os.getenv('REQUIRE_DISCORD')=='1' and not os.getenv('PUBLIC_URL','').startswith('https://'):raise SystemExit('PUBLIC_URL must be the HTTPS deployment origin')
 children=[];stop=False;exit_code=0
 def stop_signal(signum,frame):
  nonlocal stop
  stop=True
 signal.signal(signal.SIGTERM,stop_signal);signal.signal(signal.SIGINT,stop_signal)
 try:
  children.append(subprocess.Popen([sys.executable,str(ROOT/'app.py')],cwd=ROOT))
  if has_bot:children.append(subprocess.Popen([sys.executable,str(ROOT/'bot.py')],cwd=ROOT))
  else:print('Discord 연결 정보가 없어 웹만 실행합니다.',flush=True)
  started=time.monotonic();last_check=started
  while not stop:
   if any(p.poll() is not None for p in children):
    print('웹 또는 봇이 종료되어 호스팅 자동 재시작을 요청합니다.',flush=True);exit_code=1;break
   now=time.monotonic()
   if now-started>180 and now-last_check>30:
    from runtime_health import check
    try:check()
    except Exception:
     print('상태 확인 실패: 호스팅 자동 재시작을 요청합니다.',flush=True);exit_code=1;break
    last_check=now
   time.sleep(1)
 finally:
  for p in children:
   if p.poll() is None:p.terminate()
  for p in children:
   try:p.wait(timeout=10)
   except subprocess.TimeoutExpired:p.kill();p.wait()
 return exit_code
if __name__=='__main__':raise SystemExit(main())
