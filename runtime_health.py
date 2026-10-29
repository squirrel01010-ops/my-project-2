"""Liveness probe: web plus Discord heartbeat when enabled; prints no secrets."""
import http.client
import os
import sqlite3
import time

def check():
 conn=http.client.HTTPConnection('127.0.0.1',int(os.getenv('PORT','8080')),timeout=5)
 try:
  conn.request('GET','/health');response=conn.getresponse();response.read()
  if response.status!=200:raise RuntimeError('Web health check failed')
 finally:conn.close()
 if os.getenv('DISCORD_TOKEN') or os.getenv('REQUIRE_DISCORD')=='1':
  from pathlib import Path
  path=Path(os.environ.get('DB_PATH','bot.db')).expanduser()
  if not path.is_absolute():path=Path(__file__).resolve().parent/path
  with sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True) as c:
   row=c.execute("SELECT value FROM meta WHERE key='heartbeat'").fetchone()
  if not row or time.time()-float(row[0])>180:raise RuntimeError('Discord heartbeat missing')
if __name__=='__main__':
 try:check()
 except Exception as e:raise SystemExit(type(e).__name__+': service not healthy')

