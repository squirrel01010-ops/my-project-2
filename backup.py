"""Consistent online SQLite backups, including WAL transactions."""
import os
import sqlite3
import time
import tempfile
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).with_name('.env'))
import core

def create_backup():
 folder=Path(os.getenv('BACKUP_DIR',str(Path(core.DB).parent/'backups')))
 if not folder.is_absolute():folder=core.ROOT/folder
 folder.mkdir(parents=True,exist_ok=True,mode=0o700)
 target=folder/(time.strftime('orbit-%Y%m%d-%H%M%S',time.gmtime())+f'-{time.time_ns()}.sqlite3')
 # Publish only a complete backup; incomplete files never enter rotation.
 with tempfile.NamedTemporaryFile(dir=folder,prefix='.backup-',suffix='.tmp',delete=False) as handle:temporary=Path(handle.name)
 try:
  with core.db() as source:
   with sqlite3.connect(temporary) as destination:source.backup(destination)
  temporary.replace(target)
 finally:temporary.unlink(missing_ok=True)
 with core.db(True) as c:c.execute("INSERT INTO meta VALUES('last_backup',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(str(time.time()),))
 for old in sorted(folder.glob('orbit-*.sqlite3'),key=lambda p:p.stat().st_mtime_ns,reverse=True)[14:]:old.unlink()
 return target
if __name__=='__main__':print(create_backup())

