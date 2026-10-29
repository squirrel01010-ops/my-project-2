import tempfile,unittest
from unittest.mock import AsyncMock,patch
from types import SimpleNamespace
import bot,core,games

class DiscordGames(unittest.IsolatedAsyncioTestCase):
 async def test_every_command_and_button_to_completion(self):
  with tempfile.TemporaryDirectory() as d,patch.object(core,'DB',d+'/discord.db'):
   core.init()
   core.operate('123','adjust',dict(id='123',amount=1000000,key='fund'),True)
   core.operate('123','settings',dict(gameCooldown=0,key='config'),True)
   serial=0
   async def no_motion(edit,r,embed,view):await edit(embed=embed,view=view)
   with patch.object(bot,'GUILD_ID',456),patch.object(bot.game_motion,'reveal',side_effect=no_motion):
    for game,(name,_,_) in games.CATALOG.items():
     serial+=1
     i=SimpleNamespace(id=serial,guild_id=456,channel_id=789,user=SimpleNamespace(id=123,display_name='tester',roles=[]),response=SimpleNamespace(defer=AsyncMock()),edit_original_response=AsyncMock())
     command=bot.tree.get_command(name.replace(' ',''))
     args={'coin':['odd'],'dice':[3],'roulette':['red'],'horse':[2]}.get(game,[])
     await command.callback(i,100,*args)
     while True:
      embed=i.edit_original_response.await_args.kwargs['embed'];view=i.edit_original_response.await_args.kwargs['view']
      with core.db() as c:r=c.execute('SELECT * FROM game_rounds ORDER BY rowid DESC LIMIT 1').fetchone()
      if r['status']=='done':break
      self.assertTrue(view.children,game)
      b=next((b for b in view.children if b.label=='멈추기'),None) or next((b for b in view.children if b.label=='콜'),None) or next((b for b in view.children if b.label=='정산' and core.round_view(r)['state']['step']>0),None) or view.children[0]
      serial+=1
      i.id=serial;i.type=bot.discord.InteractionType.component;i.data={'custom_id':b.custom_id};i.followup=SimpleNamespace(send=AsyncMock())
      await bot.on_interaction(i)
      self.assertFalse(i.followup.send.called,game)
     self.assertIn('정산',[f.name for f in embed.fields],game)
 def test_commands_require_choices_and_validate_ranges(self):
  for name,param in [('홀짝','선택'),('주사위','숫자'),('룰렛','선택'),('경마','말번호')]:
   command=bot.tree.get_command(name);command.to_dict(bot.tree)
   self.assertTrue(next(p for p in command.parameters if p.name==param).required)


class RoleSync(unittest.IsolatedAsyncioTestCase):
 async def test_uncached_member_is_fetched_and_receives_reward(self):
  with tempfile.TemporaryDirectory() as d,patch.object(core,'DB',d+'/roles.db'):
   core.init()
   core.operate('admin','adjust',dict(id='123',amount=100,key='fund'),True)
   core.operate('admin','settings',dict(roleRewards=[dict(type='level',threshold=1,role='777')],key='roles'),True)
   member=SimpleNamespace(roles=[],nick=None,add_roles=AsyncMock(),remove_roles=AsyncMock())
   guild=SimpleNamespace(get_member=lambda uid:None,fetch_member=AsyncMock(return_value=member),get_role=lambda rid:1,me=SimpleNamespace(top_role=2))
   class RewardRole:
    managed=False
    def is_default(self):return False
    def __ge__(self,other):return False
   reward=RewardRole();guild.get_role=lambda rid:reward
   await bot.sync_roles(guild,'123')
   guild.fetch_member.assert_awaited_once_with(123)
   member.add_roles.assert_awaited_once_with(reward,reason='STELLAR 보상 동기화')
