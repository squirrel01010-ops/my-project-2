"""Consistent online SQLite backups, including WAL transactions."""
import os
import sqlite3
import time
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).with_name('.env'))
import core

def create_backup():
 folder=Path(os.getenv('BACKUP_DIR',str(Path(core.DB).parent/'backups')));folder.mkdir(parents=True,exist_ok=True,mode=0o700)
 target=folder/time.strftime('orbit-%Y%m%d-%H%M%S.sqlite3',time.gmtime())
 with core.db() as source:
  with sqlite3.connect(target) as destination:source.backup(destination)
 os.chmod(target,0o600)
 with core.db(True) as c:c.execute("INSERT INTO meta VALUES('last_backup',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(str(time.time()),))
 for old in sorted(folder.glob('orbit-*.sqlite3'),reverse=True)[14:]:old.unlink()
 return target
if __name__=='__main__':print(create_backup())
