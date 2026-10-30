"""Discord gateway worker. Run separately from app.py against the same DB_PATH."""
import asyncio
import sqlite3
import logging
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
GAME_ICONS=dict(baccarat='🃏',coin='🪙',dice='🎲',baskin='🍦',scratch='🎟️',slots='🎰',wheel='🎡',mines='💎',highlow='🃏',blackjack='♠️',roulette='🔴',indian='🪶',ttt='⭕',bomb='💣',tower='🗼',horse='🏇')
commands_synced=False

async def database(fn,write=False):
 # SQLite may wait up to 15 seconds for a lock; never wait on the gateway loop.
 def run():
  with core.db(write) as c:return fn(c)
 return await asyncio.to_thread(run)

def command_status(**values):
 with core.db(True) as c:
  if 'request' not in values:
   row=c.execute("SELECT value FROM meta WHERE key='command_sync_request'").fetchone()
   values['request']=row[0] if row else ''
  c.execute("INSERT INTO meta VALUES('command_sync',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (json.dumps(dict(values,updated=time.time(),guild_id=str(GUILD_ID),application_id=str(client.application_id or ''))),))

@tasks.loop(seconds=60)
async def sync_commands():
 global commands_synced
 if not client.is_ready():return
 row,previous=await database(lambda c:(c.execute("SELECT value FROM meta WHERE key='command_sync_request'").fetchone(),c.execute("SELECT value FROM meta WHERE key='command_sync'").fetchone()))
 request=row[0] if row else ''
 status=json.loads(previous[0]) if previous else {}
 if commands_synced and status.get('state')=='synced' and status.get('request')==request:return
 if not client.get_guild(GUILD_ID):
  await asyncio.to_thread(command_status,state='error',request=request,count=0,message='설정된 서버에 봇이 없습니다. 서버 ID와 봇 초대를 확인하세요.')
  return
 await asyncio.to_thread(command_status,state='syncing',request=request,count=0,message='서버 명령어를 등록하고 있어요.')
 try:
  guild=discord.Object(id=GUILD_ID)
  tree.copy_global_to(guild=guild)
  registered=await tree.sync(guild=guild)
  expected={c.name for c in tree.get_commands(guild=guild)}
  if {c.name for c in registered}!=expected:raise ValueError('명령어 등록 결과가 일치하지 않습니다')
 except discord.Forbidden:
  await asyncio.to_thread(command_status,state='error',request=request,count=0,message='명령어 등록 권한이 없습니다. 아래 봇 연결 버튼으로 같은 서버에 다시 승인하세요.')
 except Exception as error:
  await asyncio.to_thread(command_status,state='error',request=request,count=0,message='명령어 등록에 실패했습니다. 1분 뒤 자동 재시도합니다. ('+type(error).__name__+')')
 else:
  commands_synced=True
  await asyncio.to_thread(command_status,state='synced',request=request,count=len(registered),names=sorted(expected),message='서버 명령어 등록 완료')
  print(f'STELLAR 명령어 {len(registered)}개 등록 완료 · 서버 {GUILD_ID}',flush=True)

async def settings():
 return await database(core.settings)

def context(i):return dict(name=i.user.display_name,roles=[str(r.id) for r in getattr(i.user,'roles',[])],channel=str(i.channel_id))
async def operation(i,path,body):
 if i.guild_id!=GUILD_ID:raise ValueError('이 봇은 지정된 서버에서만 사용할 수 있어요')
 return await asyncio.to_thread(core.operate,str(i.user.id),path,{**body,'key':str(i.id)},False,context(i))

def game_embed(r):
 s=r['state'];done=r['status']=='done'
 e=discord.Embed(title=GAME_ICONS[r['game']]+' '+games.CATALOG[r['game']][0],color=0x9d85ff)
 if r['game'] in ('wheel','roulette'):
  index=s.get('segment',0) if r['game']=='wheel' else game_motion.ROULETTE_RING.index(s.get('roll',0))
  e.description=game_motion.spin_frame(r,index)
 else:e.description=game_motion.board(r)
 if s.get('message'):e.description+='\n'+s['message']
 if done:
  e.add_field(name=('📉 손실' if r['payout']<r['bet'] else f"💰 수익 (수수료 {r.get('fee',0)}%)"),value=f"**{r['payout']-r['bet']:+,}** 띵조코인",inline=True)
 else:e.add_field(name='베팅',value=f"{r['bet']:,} 띵조코인",inline=True)
 if r.get('uid'):
  with core.db() as c:balance=core.user(c,r['uid'])['xp']
  e.add_field(name='🪙 보유 코인',value=f"**{balance:,}** 띵조코인",inline=False)
 return e

def game_view(r):
 view=discord.ui.View(timeout=None)
 if r['status']=='done':
  for label,act in [('↻ 같은 금액으로','repeat'),('💰 베팅액 변경','bet'),('🎮 다른 게임','menu')]:view.add_item(discord.ui.Button(label=label,custom_id=f"replay:{r['id']}:{act}",style=discord.ButtonStyle.secondary))
  return view
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
 if await handle_replay(i):return
 if await social_bot.handle(i):return
 if i.type!=discord.InteractionType.component or not i.data.get('custom_id','').startswith('orbit:'):return
 await i.response.defer()
 try:
  _,rid,rev,act,value=i.data['custom_id'].split(':')
  if rid in game_motion.BUSY:
   return await i.followup.send('결과 연출 중이에요. 잠시 후 눌러주세요.',ephemeral=True)
  game_motion.BUSY.add(rid)
  try:
   def previous_state():
    with core.db() as c:row=c.execute('SELECT * FROM game_rounds WHERE id=? AND uid=?',(rid,str(i.user.id))).fetchone()
    return core.round_view(row)['state'] if row else {}
   previous=await asyncio.to_thread(previous_state)
   r=await operation(i,'game/action',dict(round=rid,revision=int(rev),action=act,value=int(value) if value else None))
   r['previous_state']=previous
   if act=='cashout':await i.edit_original_response(embed=await asyncio.to_thread(game_embed,r),view=game_view(r))
   else:await game_motion.reveal(i.edit_original_response,r,await asyncio.to_thread(game_embed,r),game_view(r))
  finally:game_motion.BUSY.discard(rid)
 except (ValueError,PermissionError) as e:await i.followup.send(str(e),ephemeral=True)

@tree.command(name='출석',description='오늘의 출석 띵조코인을 받아요')
async def attendance(i:discord.Interaction):
 await i.response.defer(ephemeral=True);r=await operation(i,'attendance',{})
 s=await settings();msg=s['attendanceMessage'].replace('{user}',i.user.display_name).replace('{xp}',str(r['xp'])).replace('{streak}',str(r['streak']))
 await i.followup.send(msg[:1900],ephemeral=True,allowed_mentions=discord.AllowedMentions.none())

@tree.command(name='내정보',description='현재 띵조코인와 레벨을 확인해요')
async def profile(i:discord.Interaction):
 if i.guild_id!=GUILD_ID:return await i.response.send_message('지정 서버에서 사용하세요',ephemeral=True)
 await i.response.defer(ephemeral=True)
 def read(c):
  core.ensure(c,str(i.user.id),i.user.display_name);return core.user(c,str(i.user.id))
 u=await database(read,True)
 e=discord.Embed(title=i.user.display_name,color=0x9d85ff,description=f"Lv. **{u['level']}** · **{u['xp']:,} 띵조코인**\n다음 레벨까지 {u['nextXP']-u['xp']:,} 띵조코인")
 info=await asyncio.to_thread(core.insights,str(i.user.id))
 e.title='🪪 '+i.user.display_name
 e.add_field(name='🏆 서버 순위',value=str(info['rank'])+'위')
 e.add_field(name='📅 연속 출석',value=str(info['attendance']['streak'] if info['attendance'] else 0)+'일')
 e.add_field(name='🎯 오늘 미션',value='\n'.join(m['name']+f" {m['progress']}/{m['target']}"+(' ✅' if m['claimed'] else '') for m in info['missions']['missions']),inline=False)
 v=discord.ui.View(timeout=180)
 for label,callback in [('📅 출석',attendance.callback),('🎁 보상 모두 받기',claim_all),('📊 전적',stats_command.callback)]:
  b=discord.ui.Button(label=label);b.callback=callback;v.add_item(b)
 await i.followup.send(embed=e,view=v,ephemeral=True)

@tree.command(name='랭킹',description='서버 띵조코인 상위 10명을 확인해요')
async def ranking(i:discord.Interaction):
 if i.guild_id!=GUILD_ID:return await i.response.send_message('지정 서버에서 사용하세요',ephemeral=True)
 await i.response.defer()
 d=await asyncio.to_thread(core.leaderboard);text='\n'.join(f"{n+1}. {u['name']} — Lv.{u['level']} · {u['xp']:,} 띵조코인" for n,u in enumerate(d['users'][:10])) or '아직 기록이 없어요'
 await i.followup.send(embed=discord.Embed(title='서버 리더보드',description=text,color=0x9d85ff),allowed_mentions=discord.AllowedMentions.none())

@tree.command(name='선물',description='다른 멤버에게 띵조코인을 선물해요')
async def gift(i:discord.Interaction,대상:discord.Member,금액:app_commands.Range[int,1,100000000]):
 if 대상.bot:raise ValueError('봇에게는 선물할 수 없습니다')
 await i.response.defer(ephemeral=True);r=await operation(i,'gift',dict(to=str(대상.id),amount=금액));await i.followup.send(f'{금액:,} 띵조코인 선물 완료 · 수수료 {r["fee"]:,} 띵조코인',ephemeral=True)

async def start_game(i,game,bet,choice=None):
 await i.response.defer()
 r=await operation(i,'play',dict(game=game,bet=bet,choice=choice))
 if game in ('blackjack','indian','highlow'):r['previous_state']={}
 elif games.CATALOG[game][2]:return await i.edit_original_response(embed=await asyncio.to_thread(game_embed,r),view=game_view(r))
 game_motion.BUSY.add(str(r['id']))
 try:await game_motion.reveal(i.edit_original_response,r,await asyncio.to_thread(game_embed,r),game_view(r))
 finally:game_motion.BUSY.discard(str(r['id']))

@tree.command(name='게임',description='게임별 명령어와 이용 방법을 확인해요')
async def game_help(i:discord.Interaction):
 if i.guild_id!=GUILD_ID:return await i.response.send_message('지정 서버에서 사용하세요',ephemeral=True)
 await i.response.defer(ephemeral=True)
 s=await settings()
 e=discord.Embed(title='🎮 STELLAR · 게임 라운지',description='작은 한 판, 큰 즐거움.\n`/출석`으로 띵조코인을 받고 `/내정보`에서 잔액을 확인하세요.',color=int(s['embedColor'][1:],16))
 e.add_field(name='🎲 바로 즐기는 게임',value='\n'.join(GAME_ICONS[k]+' /'+v[0].replace(' ','') for k,v in games.CATALOG.items() if not v[2]),inline=True)
 e.add_field(name='🃏 선택하며 즐기는 게임',value='\n'.join(GAME_ICONS[k]+' /'+v[0].replace(' ','') for k,v in games.CATALOG.items() if v[2]),inline=True)
 e.add_field(name='🤝 함께 즐기기',value='/홀덤 · /복권 · /크래시',inline=False)
 e.add_field(name='💎 이용 안내',value=f"최소 베팅 **{s['minBet']:,} 띵조코인** · 최대 한도 없음\n보유 코인 안에서 베팅할 수 있습니다.\n진행 중인 게임은 /이어하기로 다시 열 수 있어요." if s['casino'] else '현재 관리자가 게임을 잠시 쉬어가도록 설정했어요.',inline=False)
 e.add_field(name='🛠️ 일반 기능',value='/출석 · /내정보 · /랭킹 · /선물 · /상점 · /구매',inline=False)
 e.add_field(name='🎰 슬롯 배율',value=games.slot_rules(s['games']['slots']),inline=False)
 e.set_footer(text='✦ STELLAR · 서버 가상 띵조코인으로 즐기는 게임')
 await i.followup.send(embed=e,ephemeral=True)

@tree.command(name='도박',description='게임 라운지와 사용할 수 있는 게임 명령어를 확인해요')
async def casino_help(i:discord.Interaction):
 await game_help.callback(i)

@tree.command(name='홀짝',description='주사위가 홀수일지 짝수일지 맞혀요')
@app_commands.choices(선택=[app_commands.Choice(name='홀',value='odd'),app_commands.Choice(name='짝',value='even')])
async def coin_command(i:discord.Interaction,베팅:app_commands.Range[int,1],선택:str):
 await start_game(i,'coin',베팅,선택)

@tree.command(name='주사위',description='1~6 중 나올 숫자를 맞혀요')
async def dice_command(i:discord.Interaction,베팅:app_commands.Range[int,1],숫자:app_commands.Range[int,1,6]):
 await start_game(i,'dice',베팅,숫자)

@tree.command(name='룰렛',description='빨강·검정·제로 중 선택해 룰렛을 돌려요')
@app_commands.choices(선택=[app_commands.Choice(name='빨강',value='red'),app_commands.Choice(name='검정',value='black'),app_commands.Choice(name='제로 (0)',value='zero')])
async def roulette_command(i:discord.Interaction,베팅:app_commands.Range[int,1],선택:str):
 await start_game(i,'roulette',베팅,선택)

@tree.command(name='경마',description='1~5번 말 중 우승할 말을 골라요')
async def horse_command(i:discord.Interaction,베팅:app_commands.Range[int,1],말번호:app_commands.Range[int,1,5]):
 await start_game(i,'horse',베팅,말번호)

@tree.command(name='바카라',description='플레이어·뱅커·무승부 중 승리할 쪽을 선택해요')
@app_commands.choices(선택=[app_commands.Choice(name='플레이어',value='player'),app_commands.Choice(name='뱅커',value='banker'),app_commands.Choice(name='무승부',value='tie')])
async def baccarat_command(i:discord.Interaction,베팅:app_commands.Range[int,1],선택:str):
 await start_game(i,'baccarat',베팅,선택)

SIMPLE_GAMES={k:v[0].replace(' ','') for k,v in games.CATALOG.items() if k not in ('coin','dice','roulette','horse','baccarat')}
def register_game_command(game,name):
 async def command(i:discord.Interaction,베팅:app_commands.Range[int,1]):
  await start_game(i,game,베팅)
 tree.command(name=name,description=games.CATALOG[game][0]+' 게임을 시작해요')(command)
for game,name in SIMPLE_GAMES.items():register_game_command(game,name)

@tree.command(name='이어하기',description='진행 중인 게임의 버튼을 다시 불러와요')
async def resume(i:discord.Interaction):
 if i.guild_id!=GUILD_ID:return await i.response.send_message('지정 서버에서 사용하세요',ephemeral=True)
 await i.response.defer()
 r=await asyncio.to_thread(core.resume_game,str(i.user.id))
 if not r:return await i.followup.send('진행 중인 게임이 없어요',ephemeral=True)
 await i.followup.send(embed=await asyncio.to_thread(game_embed,r),view=game_view(r))

@tree.command(name='상점',description='구매 가능한 상품을 페이지별로 확인해요')
async def shop(i:discord.Interaction,페이지:app_commands.Range[int,1]=1):
 if i.guild_id!=GUILD_ID:return await i.response.send_message('지정 서버에서 사용하세요',ephemeral=True)
 await i.response.defer(ephemeral=True)
 result=await asyncio.to_thread(core.shop_catalog,str(i.user.id),페이지)
 text='\n'.join(f"`#{p['id']}` {p['name'][:100]} · {p['price']:,} 띵조코인"+(' · 보유 중' if p['kind']=='role' and p['owned'] else ' · 품절' if p['stock']==0 or p['kind']=='code' and p['codes']==0 else '') for p in result['products']) or '상품이 없어요'
 e=discord.Embed(title=f"상점 · {result['page']}/{result['pages']} 페이지",description=text+'\n`/구매 상품번호`로 구매하세요',color=0x9d85ff)
 view=discord.ui.View(timeout=120)
 for label,number in [('← 이전',result['page']-1),('다음 →',result['page']+1)]:
  button=discord.ui.Button(label=label,disabled=number<1 or number>result['pages'])
  async def turn(interaction,page=number):await shop.callback(interaction,page)
  button.callback=turn;view.add_item(button)
 await i.followup.send(embed=e,view=view,ephemeral=True)

@tree.command(name='구매',description='상점 상품을 구매해요')
async def buy(i:discord.Interaction,상품번호:int):
 await i.response.defer(ephemeral=True);r=await operation(i,'buy',dict(product_id=상품번호));await i.followup.send('구매 완료!'+(('\n발급 코드: '+r['code']) if r.get('code') else '\n역할이 곧 적용됩니다.'),ephemeral=True)

@tree.command(name='포인트관리',description='관리자 전용: 멤버 띵조코인 지급·차감·설정')
@app_commands.choices(작업=[app_commands.Choice(name='지급',value='give'),app_commands.Choice(name='차감',value='take'),app_commands.Choice(name='잔액 설정',value='set')])
async def manage_points(i:discord.Interaction,대상:discord.Member,작업:str,금액:app_commands.Range[int,0,100000000],사유:str='관리자 조정'):
 await i.response.defer(ephemeral=True)
 if i.guild_id!=GUILD_ID:raise PermissionError('지정 서버에서 사용하세요')
 member=await i.guild.fetch_member(i.user.id)
 roles=await i.guild.fetch_roles()
 owned={r.id for r in member.roles}
 configured=set((await settings())['adminRoles'])
 if i.user.id!=i.guild.owner_id and not configured.intersection(map(str,owned)) and not any(r.id in owned and r.permissions.administrator for r in roles):raise PermissionError('설정된 관리자 역할 또는 Discord 관리자 권한이 필요합니다')
 if 대상.bot:raise ValueError('봇의 띵조코인은 변경할 수 없습니다')
 if 작업 not in ('give','take','set'):raise ValueError('잘못된 작업입니다')
 r=await asyncio.to_thread(core.operate,str(i.user.id),'adjust',dict(id=str(대상.id),name=대상.display_name,amount=-금액 if 작업=='take' else 금액,mode='set' if 작업=='set' else 'add',reason=사유,key=str(i.id)),True,context(i))
 await i.followup.send(f'{대상.display_name} 띵조코인 변경 완료 · 현재 **{r["xp"]:,} 띵조코인** · Lv.{r["level"]}',ephemeral=True,allowed_mentions=discord.AllowedMentions.none())

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
 roles=[str(r.id) for r in getattr(message.author,'roles',[])]
 channel=message.channel;category=getattr(channel,'category_id',None) or getattr(getattr(channel,'parent',None),'category_id','')
 stamp=message.created_at.timestamp() if getattr(message,'created_at',None) else time.time()
 payload=dict(uid=str(message.author.id),name=getattr(message.author,'display_name',str(message.author)),channel=str(channel.id),roles=roles,category=str(category or ''),stamp=stamp)
 mid=getattr(message,'id',None)
 if mid is None:
  return await asyncio.to_thread(core.activity,payload['uid'],payload['name'],'chat',payload['channel'],roles,payload['category'],stamp=stamp)
 for attempt in range(6):
  try:
   await asyncio.to_thread(core.queue_chat,mid,payload)
   break
  except sqlite3.OperationalError:
   if attempt==5:raise
   await asyncio.sleep(min(4,.25*2**attempt))
 await asyncio.to_thread(core.deliver_chat,mid)

@client.event
async def on_voice_state_update(member,before,after):
 # An interruption invalidates the minute rather than granting a full minute.
 voice_candidates.discard(member.id)

@client.event
async def on_disconnect():
 voice_candidates.clear()

async def sync_roles(guild,uid):
 member=guild.get_member(int(uid))
 if member is None:
  try:member=await guild.fetch_member(int(uid))
  except discord.NotFound:return
 want,managed,u,s=await asyncio.to_thread(core.desired_roles,uid)
 have={str(r.id) for r in member.roles};add=[guild.get_role(int(x)) for x in want-have];remove=[guild.get_role(int(x)) for x in (have&managed)-want]
 for role in add+remove:
  if not role or role.is_default() or role.managed or role>=guild.me.top_role:raise ValueError('역할이 없거나 봇보다 높은 역할입니다. 역할 순서를 확인하세요')
 if add:await member.add_roles(*add,reason='STELLAR 보상 동기화')
 if remove:await member.remove_roles(*remove,reason='STELLAR 레벨/기간 변경')
 key='nick:'+uid
 row=await database(lambda c:c.execute('SELECT value FROM meta WHERE key=?',(key,)).fetchone())
 old=json.loads(row[0]) if row else None
 if s['nicknameFormat']:
  base=old['base'] if old and member.nick==old['last'] else member.nick
  nick=s['nicknameFormat'].replace('{name}',base or member.name).replace('{level}',str(u['level']))[:32]
  if nick!=member.nick:
   await member.edit(nick=nick,reason='STELLAR 레벨 표시')
   await database(lambda c:c.execute('INSERT INTO meta VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,json.dumps(dict(base=base,last=nick)))).rowcount,True)
 elif old:
  if member.nick==old['last']:await member.edit(nick=old['base'],reason='STELLAR 레벨 표시 해제')
  await database(lambda c:c.execute('DELETE FROM meta WHERE key=?',(key,)).rowcount,True)

async def send_channel(guild,channel,text,s):
 if not channel:return
 ch=guild.get_channel_or_thread(int(channel))
 if not ch:raise ValueError('채널을 찾을 수 없습니다')
 await ch.send(embed=discord.Embed(description=text[:4000],color=int(s['embedColor'][1:],16)),allowed_mentions=discord.AllowedMentions.none())

async def process_jobs(guild):
 jobs=await database(lambda c:c.execute("SELECT * FROM jobs WHERE status='pending' ORDER BY id LIMIT 40").fetchall())
 s=await settings()
 for j in jobs:
  if not await database(lambda c:c.execute("UPDATE jobs SET status='processing' WHERE id=? AND status='pending'",(j['id'],)).rowcount,True):continue
  status='done';error=''
  try:
   p=json.loads(j['payload'])
   if j['kind']=='roles':await sync_roles(guild,p['uid'])
   elif j['kind']=='all_roles':
    # Expand atomically without blocking message reception on the gateway.
    def expand(c):
     for row in c.execute('SELECT id FROM users').fetchall():core.job(c,'roles',dict(uid=row[0]))
    await database(expand,True)
   elif j['kind']=='level':
    member=guild.get_member(int(p['uid']));text=s['levelMessage'].replace('{user}',member.display_name if member else p['uid']).replace('{level}',str(p['level']))
    await send_channel(guild,s['levelChannel'],text,s)
   elif j['kind']=='purchase':
    o=await database(lambda c:c.execute('SELECT * FROM orders WHERE id=?',(p['order'],)).fetchone())
    member=guild.get_member(int(p['uid']))
    if not o:raise ValueError('구매 내역을 찾을 수 없습니다')
    if member is None:member=await guild.fetch_member(int(p['uid']))
    await member.send(f"구매 완료: {o['name']}"+(f"\n코드: {o['code']}" if o['code'] else ''),allowed_mentions=discord.AllowedMentions.none())
   elif j['kind']=='season':await send_channel(guild,s['rankingChannel'],p['name']+' 종료\n'+'\n'.join(f"{i+1}. {u['name']} · {u['score']:,} 띵조코인" for i,u in enumerate(p['ranking'])),s)
   elif j['kind']=='log':await send_channel(guild,s['logChannel'],p['text'],s)
   elif j['kind']=='social_result':await social_bot.announce(guild,p)
   elif j['kind']=='test':await send_channel(guild,p['channel'],'STELLAR 알림 테스트 · 연결이 정상입니다.',s)
  except (discord.HTTPException,ValueError) as e:status='failed';error=('Discord 권한/요청 오류: '+str(getattr(e,'status',''))) if isinstance(e,discord.HTTPException) else str(e)
  except Exception as e:status='failed';error='처리 오류: '+type(e).__name__
  await database(lambda c:c.execute('UPDATE jobs SET status=?,error=? WHERE id=?',(status,error[:500],j['id'])).rowcount,True)

async def update_ranking(guild):
 s=await settings()
 if not s['rankingChannel']:return
 r=await database(lambda c:c.execute("SELECT value FROM meta WHERE key='ranking'").fetchone())
 old=json.loads(r[0]) if r else {}
 if time.time()-old.get('time',0)<s['rankingInterval'] and old.get('channel')==s['rankingChannel']:return
 d=await asyncio.to_thread(core.leaderboard);text='\n'.join(f"{i+1}. {u['name']} · Lv.{u['level']} · {u['xp']:,} 띵조코인" for i,u in enumerate(d['users'][:20])) or '아직 활동 기록이 없어요'
 ch=guild.get_channel_or_thread(int(s['rankingChannel']))
 if not ch:raise ValueError('랭킹 채널을 찾을 수 없습니다')
 embed=discord.Embed(title='서버 띵조코인 리더보드',description=text,color=int(s['embedColor'][1:],16));msg=None
 if old.get('id') and old.get('channel')==s['rankingChannel']:
  try:msg=await ch.fetch_message(int(old['id']));await msg.edit(embed=embed)
  except discord.NotFound:pass
 if not msg:msg=await ch.send(embed=embed,allowed_mentions=discord.AllowedMentions.none())
 await database(lambda c:c.execute("INSERT INTO meta VALUES('ranking',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(json.dumps(dict(id=msg.id,channel=s['rankingChannel'],time=time.time())),)).rowcount,True)

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
  await database(lambda c:core.audit(c,'bot','worker-error',dict(type=type(e).__name__)),True)


@tasks.loop(seconds=15)
async def heartbeat_tick():
 if client.is_ready() and client.get_guild(GUILD_ID) is not None:
  def save():
   with core.db(True) as c:c.execute("INSERT INTO meta VALUES('heartbeat',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(str(time.time()),))
  await asyncio.to_thread(save)

@tasks.loop(seconds=10)
async def chat_recovery():
 await asyncio.to_thread(core.recover_chat)

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
 await database(lambda c:core.job(c,'all_roles',{}),True)

@client.event
async def on_ready():
 if not sync_commands.is_running():sync_commands.start()
 if not client.get_guild(GUILD_ID):print('지정된 서버에 봇을 초대하세요.',flush=True);return
 if not heartbeat_tick.is_running():heartbeat_tick.start()
 if not chat_recovery.is_running():chat_recovery.start()
 if not worker.is_running():worker.start()
 if not voice_tick.is_running():voice_tick.start()
 if not reconcile.is_running():reconcile.start()
 if not social_bot.live_updates.is_running():social_bot.live_updates.start()
 print('STELLAR Discord 연결 완료',flush=True)

async def main():
 await asyncio.to_thread(core.recover_jobs)
 if not GUILD_ID or not os.getenv('DISCORD_TOKEN'):raise SystemExit('DISCORD_GUILD_ID 및 DISCORD_TOKEN 환경변수가 필요합니다')
 try:
  async with client:
   await client.login(os.environ['DISCORD_TOKEN'])
   await client.connect(reconnect=True)
 except discord.PrivilegedIntentsRequired:
  message='Discord 개발자 포털의 Bot 설정에서 Server Members Intent를 켜고 봇을 재시작하세요.'
  await asyncio.to_thread(command_status,state='error',count=0,message=message)
  raise SystemExit(message)
 except discord.LoginFailure:
  message='봇 로그인에 실패했습니다. 호스팅의 DISCORD_TOKEN을 확인하세요.'
  await asyncio.to_thread(command_status,state='error',count=0,message=message)
  raise SystemExit(message)
async def claim_all(i):
 await i.response.defer(ephemeral=True)
 try:
  r=await operation(i,'mission/claim-all',{});await i.followup.send(f"🎁 {r['count']}개 미션 · +{r['reward']:,} 띵조코인",ephemeral=True)
 except (ValueError,PermissionError) as e:await command_error(i,e)

class BetModal(discord.ui.Modal):
 def __init__(self,r):
  super().__init__(title='💰 베팅액 변경');self.r=r
  self.amount=discord.ui.TextInput(label='베팅할 띵조코인',default=str(r['bet']),max_length=15);self.add_item(self.amount)
 async def on_submit(self,i):
  try:await start_game(i,self.r['game'],int(self.amount.value),self.r['state'].get('choice'))
  except (ValueError,PermissionError) as e:await command_error(i,e)

async def handle_replay(i):
 if i.type!=discord.InteractionType.component or not i.data.get('custom_id','').startswith('replay:'):return False
 try:
  _,rid,act=i.data['custom_id'].split(':')
  if i.guild_id!=GUILD_ID:raise PermissionError('지정 서버에서 사용하세요')
  row=await database(lambda c:c.execute("SELECT * FROM game_rounds WHERE id=? AND uid=? AND status='done'",(rid,str(i.user.id))).fetchone())
  if not row:raise PermissionError('본인의 게임 결과에서 사용하세요')
  r=core.round_view(row)
  if act=='menu':await game_help.callback(i)
  elif act=='bet':await i.response.send_modal(BetModal(r))
  elif act=='repeat':await start_game(i,r['game'],r['bet'],r['state'].get('choice'))
  else:raise ValueError('버튼을 확인하세요')
 except (ValueError,PermissionError) as e:await command_error(i,e)
 return True

@tree.command(name='전적',description='나의 게임별 승률·순수익·최근 결과를 확인해요')
async def stats_command(i:discord.Interaction):
 if i.guild_id!=GUILD_ID:raise PermissionError('지정 서버에서 사용하세요')
 await i.response.defer(ephemeral=True);r=await asyncio.to_thread(core.game_stats,str(i.user.id))
 e=discord.Embed(title='📊 내 게임 전적',description=r['scope'],color=0x9d85ff)
 for g in r['games']:e.add_field(name=(games.CATALOG[g['game']][0] if g['game'] in games.CATALOG else core.social.CATALOG[g['game']]['name']),value=f"{g['plays']}판 · 승률 {g['wins']/g['plays']*100:.1f}%\n💰 순수익 {g['net']:+,} · 최대 반환 {g['best']:,} 띵조코인")
 e.add_field(name='최근 결과',value='\n'.join((games.CATALOG[x['game']][0] if x['game'] in games.CATALOG else core.social.CATALOG[x['game']]['name'])+f" · {x['payout']-x['bet']:+,}" for x in r['recent'][:10]) or '아직 기록이 없어요',inline=False)
 await i.followup.send(embed=e,ephemeral=True)

@tree.command(name='미션',description='오늘의 활동 미션과 받을 보상을 확인해요')
async def mission_command(i:discord.Interaction):
 if i.guild_id!=GUILD_ID:raise PermissionError('지정 서버에서 사용하세요')
 await i.response.defer(ephemeral=True);r=await asyncio.to_thread(core.missions,str(i.user.id))
 e=discord.Embed(title='🎯 오늘의 미션',description=r['day']+' · 서버 시간대 기준',color=0x9d85ff);v=discord.ui.View(timeout=180)
 for m in r['missions']:
  e.add_field(name=m['name'],value=f"{m['progress']}/{m['target']} · 🪙 {m['reward']:,}"+(' · 수령 완료' if m['claimed'] else ''),inline=False)
  b=discord.ui.Button(label=m['name']+' 보상 받기',disabled=m['claimed'] or m['progress']<m['target'])
  async def claim(interaction,kind=m['kind']):
   await interaction.response.defer(ephemeral=True)
   try:
    result=await operation(interaction,'mission/claim',dict(kind=kind));await interaction.followup.send(f"🪙 +{result['reward']:,} 띵조코인 수령 완료",ephemeral=True)
   except (ValueError,PermissionError) as e:await command_error(interaction,e)
  b.callback=claim;v.add_item(b)
 await i.followup.send(embed=e,view=v,ephemeral=True)

@tree.command(name='주간순위',description='채팅·출석·개인 게임 주간 순위와 보상을 확인해요')
async def weekly_command(i:discord.Interaction):
 if i.guild_id!=GUILD_ID:raise PermissionError('지정 서버에서 사용하세요')
 await i.response.defer();r=await asyncio.to_thread(core.weekly_board)
 e=discord.Embed(title='🏆 주간 경쟁',description=r['day']+' ~ '+r['ends']+' (종료일 00시 정산)\n동점은 유저 ID 순 · 분야별 1~3위 보상 '+('/'.join(map(str,r['config']['rewards'])) if r['config']['enabled'] else '비활성'),color=0x9d85ff)
 for k,title in [('chat','💬 채팅'),('attendance','📅 출석'),('games','🎲 개인 게임 순수익')]:e.add_field(name=title,value='\n'.join(f"{n+1}. {u['name'][:40]} · {u['score']:+,}" for n,u in enumerate(r['rankings'][k][:10])) or '아직 기록이 없어요',inline=False)
 await i.followup.send(embed=e,allowed_mentions=discord.AllowedMentions.none())

social_bot.register(client,tree,GUILD_ID)
# A temporary database lock must not permanently stop rewards or liveness tasks.
for background in (sync_commands,heartbeat_tick,chat_recovery,worker,voice_tick,reconcile,social_bot.live_updates):
 background.add_exception_type(sqlite3.OperationalError)
for command in tree.get_commands():
 category='관리' if command.name in ('포인트관리','관리') else '기능' if command.name in ('출석','내정보','랭킹','선물','상점','구매','전적','미션','주간순위') else '게임'
 command.description=f'[{category}] '+command.description

if __name__=='__main__':asyncio.run(main())
