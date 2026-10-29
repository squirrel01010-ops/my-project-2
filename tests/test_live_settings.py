"""Dashboard saves must reach real Discord callbacks without a bot restart."""
import http.client
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import app
import bot
import core


class LiveSettings(unittest.IsolatedAsyncioTestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory()
  self.dbpatch=patch.object(core,'DB',self.tmp.name+'/live.db');self.dbpatch.start()
  core.init();self.serial=0
  self.tokenpatch=patch.object(app,'ADMIN_TOKEN','test-admin');self.tokenpatch.start()
  self.guildpatch=patch.object(bot,'GUILD_ID',456);self.guildpatch.start()
  self.server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
  self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()

 def tearDown(self):
  self.server.shutdown();self.server.server_close();self.thread.join()
  self.guildpatch.stop();self.tokenpatch.stop();self.dbpatch.stop();self.tmp.cleanup()

 def save(self,**settings):
  self.serial+=1
  conn=http.client.HTTPConnection('127.0.0.1',self.server.server_port)
  try:
   conn.request('POST','/api/settings',json.dumps(dict(settings,key=str(self.serial))),
                {'Authorization':'Bearer test-admin','Content-Type':'application/json'})
   response=conn.getresponse();body=response.read()
   self.assertEqual(response.status,200,body)
  finally:conn.close()

 def interaction(self):
  self.serial+=1
  return SimpleNamespace(id=self.serial,guild_id=456,channel_id=789,
   user=SimpleNamespace(id=123,display_name='tester',roles=[],bot=False),
   response=SimpleNamespace(defer=AsyncMock()),followup=SimpleNamespace(send=AsyncMock()),
   edit_original_response=AsyncMock())

 async def test_attendance_and_chat_use_saved_rewards_immediately(self):
  self.save(attendanceXP=321,attendanceMessage='{user}: +{xp} / {streak}',chatXP=77,cooldown=0,dailyCap=100)
  i=self.interaction();await bot.attendance.callback(i)
  self.assertEqual(i.followup.send.await_args.args[0],'tester: +321 / 1')
  message=SimpleNamespace(guild=SimpleNamespace(id=456),author=i.user,
                          channel=SimpleNamespace(id=789,category_id=None))
  await bot.on_message(message);await bot.on_message(message)
  with core.db() as c:self.assertEqual(core.user(c,'123')['xp'],475)
  self.save(chatXP=13,dailyCap=0)
  await bot.on_message(message)
  with core.db() as c:self.assertEqual(core.user(c,'123')['xp'],488)
  with self.assertRaisesRegex(ValueError,'이미 출석'):await bot.attendance.callback(self.interaction())
  self.save(excludedChannels=['789'])
  await bot.on_message(message)
  with core.db() as c:self.assertEqual(core.user(c,'123')['xp'],501)

 async def test_casino_saved_limits_roles_channels_and_enable_switch(self):
  self.save(attendanceXP=1000,gameCooldown=0,minBet=10,maxBet=500,casinoRoles=['55'],casinoChannels=['789'])
  i=self.interaction();await bot.attendance.callback(i)
  with self.assertRaisesRegex(PermissionError,'역할'):await bot.coin_command.callback(self.interaction(),100,'odd')
  i=self.interaction();i.user.roles=[SimpleNamespace(id=55)];i.channel_id=999
  with self.assertRaisesRegex(PermissionError,'채널'):await bot.coin_command.callback(i,100,'odd')
  i=self.interaction();i.user.roles=[SimpleNamespace(id=55)]
  async def reveal(edit,r,embed,view):await edit(embed=embed,view=view)
  with patch.object(bot.game_motion,'reveal',side_effect=reveal):
   await bot.coin_command.callback(i,100,'odd')
  i.edit_original_response.assert_awaited_once()
  with core.db() as c:self.assertEqual(c.execute('SELECT status FROM game_rounds').fetchone()[0],'done')
  self.save(casino=False)
  with self.assertRaisesRegex(ValueError,'비활성화'):await bot.coin_command.callback(self.interaction(),100,'odd')

 async def test_expired_game_does_not_block_next_game_without_worker(self):
  self.save(attendanceXP=1000,gameCooldown=0)
  await bot.attendance.callback(self.interaction())
  r=core.operate('123','play',dict(game='mines',bet=100,key='old'))
  with core.db(True) as c:c.execute('UPDATE game_rounds SET expires=0 WHERE id=?',(r['id'],))
  core.operate('123','play',dict(game='coin',choice='odd',bet=100,key='new'))
  with core.db() as c:
   self.assertEqual(c.execute("SELECT COUNT(*) FROM game_rounds WHERE status='done'").fetchone()[0],2)

 def test_database_path_does_not_depend_on_working_directory(self):
  before=Path.cwd()
  try:
   os.chdir(self.tmp.name)
   with patch.dict(os.environ,{'DB_PATH':'shared/bot.db'}):
    self.assertEqual(core.database_path(),str(core.ROOT/'shared/bot.db'))
   with patch.dict(os.environ,{'DB_PATH':self.tmp.name+'/absolute.db'}):
    self.assertEqual(core.database_path(),self.tmp.name+'/absolute.db')
  finally:os.chdir(before)
