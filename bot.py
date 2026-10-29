"""Discord gateway worker. Run separately from app.py against the same DB_PATH."""
import asyncio
import json
import os
import time
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).with_name('.env'))
import discord
from discord import app_commands
from discord.ext import tasks
import core
import games
import social_bot
import game_motion

GUILD_ID=int(os.getenv('DISCORD_GUILD_ID','0'))
intents=discord.Intents.default();intents.members=True;intents.voice_states=True;intents.messages=True
client=discord.Client(intents=intents, proxy=os.getenv("HTTPS_PROXY") or None)
tree=app_commands.CommandTree(client)
voice_candidates=set()

async def settings():
 with core.db() as c:return core.settings(c)

def context(i):return dict(name=i.user.display_name,roles=[str(r.id) for r in getattr(i.user,'roles',[])],channel=str(i.channel_id))
async def operation(i,path,body):
 if i.guild_id!=GUILD_ID:raise ValueError('이 봇은 지정된 서버에서만 사용할 수 있어요')
 return await asyncio.to_thread(core.operate,str(i.user.id),path,{**body,'key':str(i.id)},False,context(i))

def game_embed(r):
 s=r['state'];e=discord.Embed(title=games.CATALOG[r['game']][0],color=0x9d85ff)
 e.description=f"베팅 **{r['bet']:,} EXP** · {'종료' if r['status']=='done' else '진행 중'}\n{s.get('message','')}"
 for k,label in [('roll','결과'),('symbols','릴'),('order','도착 순서'),('card','현재 카드'),('count','현재 숫자'),('player','내 카드'),('dealer','상대 카드'),('opened','선택한 칸'),('board','보드')]:
  if k not in s:continue
  value=s[k]
  card=lambda n:'🂠' if n is None else str({1:'A',11:'J',12:'Q',13:'K'}.get(n,n))
  if k=='symbols':value=' │ '.join(['🍒','🍋','🔔','⭐','💎'][n] for n in value)
  elif k=='order':value=' → '.join(f'{n}번 🐎' for n in value)
  elif k in ('player','dealer'):value=' '.join(map(card,value)) if isinstance(value,list) else card(value)
  elif k=='card':value=card(value)
  elif k=='opened':value=' · '.join(str(n+1)+'번' for n in value) or '아직 선택하지 않았어요'
  elif k=='board':value='\n'.join(' '.join(value[n+j] or '⬜' for j in range(3)) for n in (0,3,6))
  e.add_field(name=label,value=str(value)[:1024],inline=False)
 if r['status']=='done':e.add_field(name='정산',value=f"반환 {r['payout']:,} EXP · 순손익 {r['payout']-r['bet']:+,} EXP")
 elif s.get('mult',0):e.add_field(name='현재 원금 포함 배당',value=f"{s['mult']:.3f}배 (수익 수수료 {r['fee']}%)")
 e.set_footer(text='게임 시간이 지나면 베팅금이 소멸합니다. /이어하기로 복구할 수 있어요.')
 return e

def game_view(r):
 view=discord.ui.View(timeout=None)
 if r['status']=='done':return view
 s=r['state'];g=r['game'];controls=[]
 if g=='blackjack':controls=[('카드 받기','hit',''),('멈추기','stand','')]
 elif g=='indian':controls=[('콜','call',''),('폴드','fold','')]
 elif g=='highlow':
  controls=([('높음','higher','')] if s['card']<13 else [])+([('낮음','lower','')] if s['card']>1 else [])+[('정산','cashout','')]
 elif g=='baskin':controls=[(str(n)+'개 세기','count',str(n)) for n in (1,2,3)]
 elif g in ('mines','bomb','tower','ttt'):
  n={'mines':9,'bomb':5,'tower':3,'ttt':9}[g]
  controls=[(str(n+1),'pick',str(n)) for n in range(n) if (g not in ('mines','bomb') or n not in s['opened']) and (g!='ttt' or not s['board'][n])]
  if g!='ttt':controls.append(('정산','cashout',''))
 for label,act,value in controls:
  view.add_item(discord.ui.Button(label=label,custom_id=f"orbit:{r['id']}:{r['revision']}:{act}:{value}",style=discord.ButtonStyle.primary if act=='cashout' else discord.ButtonStyle.secondary))
 return view

@client.event
async def on_interaction(i):
 if await social_bot.handle(i):return
 if i.type!=discord.InteractionType.component or not i.data.get('custom_id','').startswith('orbit:'):return
 await i.response.defer()
 try:
  _,rid,rev,act,value=i.data['custom_id'].split(':')
  if rid in game_motion.BUSY:
   return await i.followup.send('결과 연출 중이에요. 잠시 후 눌러주세요.',ephemeral=True)
  game_motion.BUSY.add(rid)
  try:
   r=await operation(i,'game/action',dict(round=rid,revision=int(rev),action=act,value=int(value) if value else None))
   if act=='cashout':await i.edit_original_response(embed=game_embed(r),view=game_view(r))
   else:await game_motion.reveal(i.edit_original_response,r,game_embed(r),game_view(r))
  finally:game_motion.BUSY.discard(rid)
 except (ValueError,PermissionError) as e:await i.followup.send(str(e),ephemeral=True)

@tree.command(name='출석',description='오늘의 출석 경험치를 받아요')
async def attendance(i:discord.Interaction):
 await i.response.defer(ephemeral=True);r=await operation(i,'attendance',{})
 s=await settings();msg=s['attendanceMessage'].replace('{user}',i.user.display_name).replace('{xp}',str(r['xp'])).replace('{streak}',str(r['streak']))
 await i.followup.send(msg[:1900],ephemeral=True,allowed_mentions=discord.AllowedMentions.none())

@tree.command(name='내정보',description='현재 경험치와 레벨을 확인해요')
async def profile(i:discord.Interaction):
 if i.guild_id!=GUILD_ID:return await i.response.send_message('지정 서버에서 사용하세요',ephemeral=True)
 with core.db(True) as c:core.ensure(c,str(i.user.id),i.user.display_name);u=core.user(c,str(i.user.id))
 e=discord.Embed(title=i.user.display_name,color=0x9d85ff,description=f"Lv. **{u['level']}** · **{u['xp']:,} EXP**\n다음 레벨까지 {u['nextXP']-u['xp']:,} EXP")
 await i.response.send_message(embed=e,ephemeral=True)

@tree.command(name='랭킹',description='서버 경험치 상위 10명을 확인해요')
async def ranking(i:discord.Interaction):
 if i.guild_id!=GUILD_ID:return await i.response.send_message('지정 서버에서 사용하세요',ephemeral=True)
 d=await asyncio.to_thread(core.state);text='\n'.join(f"{n+1}. {u['name']} — Lv.{u['level']} · {u['xp']:,} EXP" for n,u in enumerate(d['users'][:10])) or '아직 기록이 없어요'
 await i.response.send_message(embed=discord.Embed(title='서버 리더보드',description=text,color=0x9d85ff),allowed_mentions=discord.AllowedMentions.none())

@tree.command(name='선물',description='다른 멤버에게 경험치를 선물해요')
async def gift(i:discord.Interaction,대상:discord.Member,금액:app_commands.Range[int,1,100000000]):
 if 대상.bot:raise ValueError('봇에게는 선물할 수 없습니다')
 await i.response.defer(ephemeral=True);r=await operation(i,'gift',dict(to=str(대상.id),amount=금액));await i.followup.send(f'{금액:,} EXP 선물 완료 · 수수료 {r["fee"]:,} EXP',ephemeral=True)

async def start_game(i,game,bet,choice=None):
 await i.response.defer()
 r=await operation(i,'play',dict(game=game,bet=bet,choice=choice))
 game_motion.BUSY.add(str(r['id']))
 try:await game_motion.reveal(i.edit_original_response,r,game_embed(r),game_view(r))
 finally:game_motion.BUSY.discard(str(r['id']))

@tree.command(name='게임',description='게임별 명령어와 이용 방법을 확인해요')
async def game_help(i:discord.Interaction):
 await i.response.send_message('🎮 **게임 명령어**\n'+ '\n'.join('/'+v[0].replace(' ','')+' — '+v[1] for v in games.CATALOG.values())+'\n/홀덤 · /복권 · /크래시\n진행 중인 게임은 /이어하기로 다시 열 수 있어요.',ephemeral=True)

@tree.command(name='홀짝',description='주사위가 홀수일지 짝수일지 맞혀요')
@app_commands.choices(선택=[app_commands.Choice(name='홀',value='odd'),app_commands.Choice(name='짝',value='even')])
async def coin_command(i:discord.Interaction,베팅:app_commands.Range[int,1,1000000],선택:str):
 await start_game(i,'coin',베팅,선택)

@tree.command(name='주사위',description='1~6 중 나올 숫자를 맞혀요')
async def dice_command(i:discord.Interaction,베팅:app_commands.Range[int,1,1000000],숫자:app_commands.Range[int,1,6]):
 await start_game(i,'dice',베팅,숫자)

@tree.command(name='룰렛',description='빨강·검정·제로 중 선택해 룰렛을 돌려요')
@app_commands.choices(선택=[app_commands.Choice(name='빨강',value='red'),app_commands.Choice(name='검정',value='black'),app_commands.Choice(name='제로 (0)',value='zero')])
async def roulette_command(i:discord.Interaction,베팅:app_commands.Range[int,1,1000000],선택:str):
 await start_game(i,'roulette',베팅,선택)

@tree.command(name='경마',description='1~5번 말 중 우승할 말을 골라요')
async def horse_command(i:discord.Interaction,베팅:app_commands.Range[int,1,1000000],말번호:app_commands.Range[int,1,5]):
 await start_game(i,'horse',베팅,말번호)

SIMPLE_GAMES={k:v[0].replace(' ','') for k,v in games.CATALOG.items() if k not in ('coin','dice','roulette','horse')}
def register_game_command(game,name):
 async def command(i:discord.Interaction,베팅:app_commands.Range[int,1,1000000]):
  await start_game(i,game,베팅)
 tree.command(name=name,description=games.CATALOG[game][0]+' 게임을 시작해요')(command)
for game,name in SIMPLE_GAMES.items():register_game_command(game,name)

@tree.command(name='이어하기',description='진행 중인 게임의 버튼을 다시 불러와요')
async def resume(i:discord.Interaction):
 if i.guild_id!=GUILD_ID:return await i.response.send_message('지정 서버에서 사용하세요',ephemeral=True)
 with core.db() as c:r=c.execute("SELECT * FROM game_rounds WHERE uid=? AND status='active'",(str(i.user.id),)).fetchone()
 if not r:return await i.response.send_message('진행 중인 게임이 없어요',ephemeral=True)
 r=core.round_view(r);await i.response.send_message(embed=game_embed(r),view=game_view(r))

@tree.command(name='상점',description='구매 가능한 상품을 확인해요')
async def shop(i:discord.Interaction):
 if i.guild_id!=GUILD_ID:return await i.response.send_message('지정 서버에서 사용하세요',ephemeral=True)
 with core.db() as c:products=c.execute('SELECT * FROM products WHERE active=1 ORDER BY id LIMIT 25').fetchall()
 text='\n'.join(f"`#{p['id']}` {p['name']} · {p['price']:,} EXP" for p in products) or '등록된 상품이 없어요'
 await i.response.send_message(embed=discord.Embed(title='경험치 상점',description=text+'\n`/구매 상품번호`로 구매하세요',color=0x9d85ff),ephemeral=True)

@tree.command(name='구매',description='상점 상품을 구매해요')
async def buy(i:discord.Interaction,상품번호:int):
 await i.response.defer(ephemeral=True);r=await operation(i,'buy',dict(product_id=상품번호));await i.followup.send('구매 완료!'+(('\n발급 코드: '+r['code']) if r.get('code') else '\n역할이 곧 적용됩니다.'),ephemeral=True)

@tree.command(name='포인트관리',description='관리자 전용: 멤버 포인트 지급·차감·설정')
@app_commands.default_permissions(administrator=True)
@app_commands.choices(작업=[app_commands.Choice(name='지급',value='give'),app_commands.Choice(name='차감',value='take'),app_commands.Choice(name='잔액 설정',value='set')])
async def manage_points(i:discord.Interaction,대상:discord.Member,작업:str,금액:app_commands.Range[int,0,100000000],사유:str='관리자 조정'):
 await i.response.defer(ephemeral=True)
 if i.guild_id!=GUILD_ID:raise PermissionError('지정 서버에서 사용하세요')
 member=await i.guild.fetch_member(i.user.id)
 roles=await i.guild.fetch_roles()
 owned={r.id for r in member.roles}
 if i.user.id!=i.guild.owner_id and not any(r.id in owned and r.permissions.administrator for r in roles):raise PermissionError('관리자 권한이 있는 역할이 필요합니다')
 if 대상.bot:raise ValueError('봇의 포인트는 변경할 수 없습니다')
 if 작업 not in ('give','take','set'):raise ValueError('잘못된 작업입니다')
 r=await asyncio.to_thread(core.operate,str(i.user.id),'adjust',dict(id=str(대상.id),name=대상.display_name,amount=-금액 if 작업=='take' else 금액,mode='set' if 작업=='set' else 'add',reason=사유,key=str(i.id)),True,context(i))
 await i.followup.send(f'{대상.display_name} 포인트 변경 완료 · 현재 **{r["xp"]:,} EXP** · Lv.{r["level"]}',ephemeral=True,allowed_mentions=discord.AllowedMentions.none())

@tree.command(name='관리',description='웹 관리 사이트를 열어요')
async def dashboard(i:discord.Interaction):
 await i.response.send_message(os.getenv('PUBLIC_URL','http://127.0.0.1:8080'),ephemeral=True)

@tree.error
async def command_error(i,error):
 error=getattr(error,'original',error);msg=str(error) if isinstance(error,(ValueError,PermissionError)) else '요청을 처리하지 못했습니다. 잠시 후 다시 시도하세요.'
 if i.response.is_done():await i.followup.send(msg,ephemeral=True)
 else:await i.response.send_message(msg,ephemeral=True)

@client.event
async def on_message(message):
 if not message.guild or message.guild.id!=GUILD_ID or message.author.bot:return
 await asyncio.to_thread(core.activity,str(message.author.id),message.author.display_name,'chat',str(message.channel.id),[str(r.id) for r in message.author.roles],str(message.channel.category_id or ''))

@client.event
async def on_voice_state_update(member,before,after):
 # An interruption invalidates the minute rather than granting a full minute.
 voice_candidates.discard(member.id)

@client.event
async def on_disconnect():
 voice_candidates.clear()

async def sync_roles(guild,uid):
 member=guild.get_member(int(uid))
 if not member:return
 want,managed,u,s=await asyncio.to_thread(core.desired_roles,uid)
 have={str(r.id) for r in member.roles};add=[guild.get_role(int(x)) for x in want-have];remove=[guild.get_role(int(x)) for x in (have&managed)-want]
 for role in add+remove:
  if not role or role.is_default() or role.managed or role>=guild.me.top_role:raise ValueError('역할이 없거나 봇보다 높은 역할입니다. 역할 순서를 확인하세요')
 if add:await member.add_roles(*add,reason='STELLAR 보상 동기화')
 if remove:await member.remove_roles(*remove,reason='STELLAR 레벨/기간 변경')
 key='nick:'+uid
 with core.db() as c:row=c.execute('SELECT value FROM meta WHERE key=?',(key,)).fetchone()
 old=json.loads(row[0]) if row else None
 if s['nicknameFormat']:
  base=old['base'] if old and member.nick==old['last'] else member.nick
  nick=s['nicknameFormat'].replace('{name}',base or member.name).replace('{level}',str(u['level']))[:32]
  if nick!=member.nick:
   await member.edit(nick=nick,reason='STELLAR 레벨 표시')
   with core.db(True) as c:c.execute('INSERT INTO meta VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,json.dumps(dict(base=base,last=nick))))
 elif old:
  if member.nick==old['last']:await member.edit(nick=old['base'],reason='STELLAR 레벨 표시 해제')
  with core.db(True) as c:c.execute('DELETE FROM meta WHERE key=?',(key,))

async def send_channel(guild,channel,text,s):
 if not channel:return
 ch=guild.get_channel(int(channel))
 if not ch:raise ValueError('채널을 찾을 수 없습니다')
 await ch.send(embed=discord.Embed(description=text[:4000],color=int(s['embedColor'][1:],16)),allowed_mentions=discord.AllowedMentions.none())

async def process_jobs(guild):
 with core.db() as c:jobs=c.execute("SELECT * FROM jobs WHERE status='pending' ORDER BY id LIMIT 40").fetchall()
 s=await settings()
 for j in jobs:
  p=json.loads(j['payload']);status='done';error=''
  try:
   if j['kind']=='roles':await sync_roles(guild,p['uid'])
   elif j['kind']=='all_roles':
    with core.db() as c:uids=[r[0] for r in c.execute('SELECT id FROM users')]
    # Expand into individual retryable jobs so one bad role never blocks all members.
    with core.db(True) as c:
     for uid in uids:core.job(c,'roles',dict(uid=uid))
   elif j['kind']=='level':
    member=guild.get_member(int(p['uid']));text=s['levelMessage'].replace('{user}',member.display_name if member else p['uid']).replace('{level}',str(p['level']))
    await send_channel(guild,s['levelChannel'],text,s)
   elif j['kind']=='purchase':
    with core.db() as c:o=c.execute('SELECT * FROM orders WHERE id=?',(p['order'],)).fetchone()
    member=guild.get_member(int(p['uid']))
    if member and o:await member.send(f"구매 완료: {o['name']}"+(f"\n코드: {o['code']}" if o['code'] else ''),allowed_mentions=discord.AllowedMentions.none())
   elif j['kind']=='season':await send_channel(guild,s['rankingChannel'],p['name']+' 종료\n'+'\n'.join(f"{i+1}. {u['name']} · {u['score']:,} EXP" for i,u in enumerate(p['ranking'])),s)
   elif j['kind']=='log':await send_channel(guild,s['logChannel'],p['text'],s)
   elif j['kind']=='social_result':await social_bot.announce(guild,p)
   elif j['kind']=='test':await send_channel(guild,p['channel'],'STELLAR 알림 테스트 · 연결이 정상입니다.',s)
  except (discord.HTTPException,ValueError) as e:status='failed';error=('Discord 권한/요청 오류: '+str(getattr(e,'status',''))) if isinstance(e,discord.HTTPException) else str(e)
  with core.db(True) as c:c.execute('UPDATE jobs SET status=?,error=? WHERE id=?',(status,error[:500],j['id']))

async def update_ranking(guild):
 s=await settings()
 if not s['rankingChannel']:return
 with core.db() as c:r=c.execute("SELECT value FROM meta WHERE key='ranking'").fetchone()
 old=json.loads(r[0]) if r else {}
 if time.time()-old.get('time',0)<s['rankingInterval'] and old.get('channel')==s['rankingChannel']:return
 d=await asyncio.to_thread(core.state);text='\n'.join(f"{i+1}. {u['name']} · Lv.{u['level']} · {u['xp']:,} EXP" for i,u in enumerate(d['users'][:20])) or '아직 활동 기록이 없어요'
 ch=guild.get_channel(int(s['rankingChannel']))
 if not ch:raise ValueError('랭킹 채널을 찾을 수 없습니다')
 embed=discord.Embed(title='서버 경험치 리더보드',description=text,color=int(s['embedColor'][1:],16));msg=None
 if old.get('id') and old.get('channel')==s['rankingChannel']:
  try:msg=await ch.fetch_message(int(old['id']));await msg.edit(embed=embed)
  except discord.NotFound:pass
 if not msg:msg=await ch.send(embed=embed,allowed_mentions=discord.AllowedMentions.none())
 with core.db(True) as c:c.execute("INSERT INTO meta VALUES('ranking',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(json.dumps(dict(id=msg.id,channel=s['rankingChannel'],time=time.time())),))

@tasks.loop(seconds=15)
async def worker():
 if not client.is_ready():return
 guild=client.get_guild(GUILD_ID)
 if not guild:return
 try:
  await asyncio.to_thread(core.maintenance)
  await process_jobs(guild)
  await update_ranking(guild)
 except Exception as e:
  with core.db(True) as c:core.audit(c,'bot','worker-error',dict(type=type(e).__name__))
 with core.db(True) as c:c.execute("INSERT INTO meta VALUES('heartbeat',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(str(time.time()),))

@tasks.loop(seconds=60)
async def voice_tick():
 global voice_candidates
 if not client.is_ready():
  voice_candidates.clear();return
 guild=client.get_guild(GUILD_ID)
 if not guild:return
 s=await settings();now=set()
 for ch in list(guild.voice_channels)+list(guild.stage_channels):
  if ch==guild.afk_channel:continue
  humans=[m for m in ch.members if not m.bot]
  if len(humans)<s['voiceMinMembers']:continue
  for m in humans:
   v=m.voice
   if not v or v.suppress or (not s['voiceAllowMuted'] and (v.mute or v.self_mute)) or (not s['voiceAllowDeafened'] and (v.deaf or v.self_deaf)):continue
   now.add(m.id)
   if m.id in voice_candidates:await asyncio.to_thread(core.activity,str(m.id),m.display_name,'voice',str(ch.id),[str(r.id) for r in m.roles],str(ch.category_id or ''))
 voice_candidates=now

@tasks.loop(minutes=5)
async def reconcile():
 with core.db(True) as c:core.job(c,'all_roles',{})

@client.event
async def on_ready():
 if not client.get_guild(GUILD_ID):print('지정된 서버에 봇을 초대하세요.',flush=True);return
 if not worker.is_running():worker.start()
 if not voice_tick.is_running():voice_tick.start()
 if not reconcile.is_running():reconcile.start()
 if not social_bot.live_updates.is_running():social_bot.live_updates.start()
 print('STELLAR Discord 연결 완료',flush=True)

async def main():
 if not GUILD_ID or not os.getenv('DISCORD_TOKEN'):raise SystemExit('DISCORD_GUILD_ID 및 DISCORD_TOKEN 환경변수가 필요합니다')
 async with client:
  await client.login(os.environ['DISCORD_TOKEN'])
  guild=discord.Object(id=GUILD_ID);tree.copy_global_to(guild=guild);await tree.sync(guild=guild)
  await client.connect(reconnect=True)
social_bot.register(client,tree,GUILD_ID)
if __name__=='__main__':asyncio.run(main())
