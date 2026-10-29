"""Discord text/button UI for multiplayer tables, draws and crash rounds."""
import asyncio
import json
import time
import discord
from discord import app_commands
from discord.ext import tasks
import core
import social

CLIENT=None
GUILD_ID=0

def context(i):return dict(name=i.user.display_name,roles=[str(r.id) for r in getattr(i.user,'roles',[])],channel=str(i.channel_id))
async def op(i,path,b):
 if i.guild_id!=GUILD_ID:raise ValueError('지정된 서버에서 사용하세요')
 return await asyncio.to_thread(core.operate,str(i.user.id),path,{**b,'key':str(i.id)},False,context(i))

STATUS={'lobby':'참가자 모집 중','active':'게임 진행 중','open':'복권 판매 중','flying':'비행 중','done':'게임 종료','cancelled':'취소됨'}
STREET={'preflop':'첫 베팅','flop':'플롭','turn':'턴','river':'리버'}

def balance_text(uid):
 with core.db() as c:row=c.execute('SELECT xp FROM users WHERE id=?',(uid,)).fetchone()
 return f"🪙 보유 코인 **{row[0]:,}** 띵조코인" if row else ''

def embed(s):
 kind=s['kind'];e=discord.Embed(title=social.CATALOG[kind]['name'],color=0xa28aff)
 if kind=='holdem':
  e.description=f"바이인 **{s['buyin']:,} 띵조코인** · SB/BB **{max(1,s['blind']//2)}/{s['blind']}**\n상태: **{STATUS.get(s['status'],'준비 중')}**"
  if s['status']=='lobby':e.description+=f"\n모집 마감 <t:{int(s['lobby_end'])}:R> · 2명 이상이면 자동 시작"
  else:
   e.add_field(name='공용 카드',value=' '.join(s.get('board',[])) or '🂠 🂠 🂠 🂠 🂠',inline=False)
   e.add_field(name='팟',value=f"{sum(p.get('total',0) for p in s['players']):,} 띵조코인 · {STREET.get(s.get('street'),'')}")
   if s['status']=='active':e.add_field(name='현재 차례',value=f"{s['players'][s['turn']]['name']} · <t:{int(s['deadline'])}:R>")
  for p in s['players']:
   cards=' '.join(p.get('cards',[]));line=f"남은 칩 {p['stack']:,} · 이번 라운드 {p.get('round',0):,}"+(' · 폴드' if p.get('folded') else '')
   if s['status']=='done':line=f"💰 수익 {s['payouts'].get(p['uid'],0)-s['buyin']:+,} 띵조코인 (수수료 0%)\n"+balance_text(p['uid'])
   e.add_field(name=p['name'][:100],value=f'{cards}\n{line}',inline=False)
  e.set_footer(text='내 패는 [내 카드]에서만 비공개 확인 · 턴 초과 시 가능하면 체크, 아니면 폴드')
 elif kind=='lottery':
  e.description=f"🎟 1장 **{s['price']:,} 띵조코인** · 1인 최대 {s['max_tickets']}장\n추첨 <t:{int(s['draw_at'])}:F>\n상금 적립 {s['pot']+s['rollover']:,} 띵조코인 (이번 판매분 수수료 {s['fee']}%)"
  if s['status']=='done':e.add_field(name='당첨 번호',value=' · '.join(map(str,s['winning'])));e.add_field(name='결과',value=f"당첨권 {len(s['winners'])}장 · 지급 {s['paid']:,} 띵조코인")
  e.set_footer(text='1~20 중 서로 다른 3개 · 모두 일치하면 당첨 · 당첨자가 없으면 이월')
 else:
  e.description=(f"🚀 출발 <t:{int(s['starts'])}:R>" if s['status']=='lobby' else f"{'💥 종료' if s['status']=='done' else '🚀 비행 중'} **{(s.get('crash',s['multiplier']) if s['status']=='done' else s['multiplier']):.2f}배**")
  lines=[]
  for p in s['players'][:25]:
   status=f"✅ {p.get('at',0):.2f}배 정산" if p['status']=='cashed' else '💥 패배' if p['status']=='lost' else f"자동 {p['auto']/100:.2f}배" if p['auto'] else '수동 정산'
   lines.append(f"{p['name'][:30]} · {status}\n💰 수익 {(p.get('payout',0)-p['bet'] if p['status'] in ('cashed','lost') else 0):+,} 띵조코인 (수수료 0%)\n"+balance_text(p['uid']))
  e.add_field(name=f"참가자 {len(s['players'])}명",value='\n'.join(lines)[:1024] or '모집 중',inline=False)
  e.set_footer(text='자동 정산 배당을 정해 두면 목표 배당에서 자동으로 정산돼요.')
 return e

def view(s):
 v=discord.ui.View(timeout=None);kind=s['kind'];rid=s['id'];controls=[]
 if kind=='holdem':
  if s['status']=='lobby':controls=[('참가','join'),('시작 (방장)','start'),('나가기','leave')]
  elif s['status']=='active':controls=[('체크','check'),('콜','call'),('레이즈','raise'),('올인','allin'),('폴드','fold')]
  if s['status'] not in ('cancelled',):controls.append(('내 카드','cards'))
 elif kind=='lottery' and s['status']=='open':controls=[('자동 1장 구매','auto'),('번호 선택 구매','numbers'),('내 복권','tickets')]
 elif kind=='crash':
  if s['status']=='lobby':controls=[('참가','join')]
  elif s['status']=='flying':controls=[('지금 정산','cashout')]
 controls.append(('새로고침','refresh'))
 for label,action in controls:v.add_item(discord.ui.Button(label=label,custom_id=f"social:{kind}:{rid}:{action}:{s.get('revision',0)}",style=discord.ButtonStyle.primary if action in ('cashout','join','auto') else discord.ButtonStyle.secondary))
 return v

async def bind_message(s,message):
 with core.db(True) as c:c.execute('UPDATE live_games SET channel=?,message=? WHERE id=?',(str(message.channel.id),str(message.id),s['id']))

async def publish(i,s):
 # Always rebuild a public snapshot: operation results may contain the caller's hole cards.
 public=await asyncio.to_thread(social.read,s['kind'],s['id'])
 with core.db() as c:existing=c.execute('SELECT channel,message FROM live_games WHERE id=?',(s['id'],)).fetchone()
 if existing and existing['message'] and existing['channel']==str(i.channel_id):
  try:
   msg=i.channel.get_partial_message(int(existing['message']))
   await msg.edit(embed=embed(public),view=view(public),allowed_mentions=discord.AllowedMentions.none())
   await i.followup.send('진행 화면: '+msg.jump_url,ephemeral=True);return
  except discord.NotFound:pass
 msg=await i.followup.send(embed=embed(public),view=view(public),wait=True,allowed_mentions=discord.AllowedMentions.none());await bind_message(public,msg)

async def update_message(i,s):
 public=await asyncio.to_thread(social.read,s['kind'],s['id'])
 await i.edit_original_response(embed=embed(public),view=view(public),allowed_mentions=discord.AllowedMentions.none())

class InputModal(discord.ui.Modal):
 def __init__(self,kind,rid,action,revision):
  super().__init__(title={'holdem':'레이즈 총액','lottery':'복권 번호 선택','crash':'크래시 참가'}[kind]);self.kind=kind;self.rid=rid;self.action=action;self.revision=revision
  self.amount=discord.ui.TextInput(label='이번 라운드 총 베팅액' if kind=='holdem' else '번호 3개 (예: 1 7 20)' if kind=='lottery' else '베팅 띵조코인',max_length=50);self.add_item(self.amount)
  if kind=='crash':self.auto=discord.ui.TextInput(label='자동 정산 배당 (0=수동, 예: 2.00)',default='2.00',max_length=10);self.add_item(self.auto)
 async def on_submit(self,i):
  await i.response.defer(ephemeral=True)
  try:
   if self.kind=='holdem':s=await op(i,'holdem/action',dict(table=self.rid,revision=self.revision,action='raise',amount=int(self.amount.value)))
   elif self.kind=='lottery':
    s=await op(i,'lottery/buy',dict(draw=self.rid,numbers=[int(x) for x in self.amount.value.replace(',',' ').split()]))
    return await i.followup.send('구매 번호: '+str(s['tickets'][0]['numbers']),ephemeral=True)
   else:
    value=float(self.auto.value);cents=round(value*100)
    s=await op(i,'crash/join',dict(round=self.rid,bet=int(self.amount.value),auto=cents))
   await i.followup.send('반영했습니다. 테이블에서 새로고침하면 확인할 수 있어요.',ephemeral=True)
  except (ValueError,PermissionError,OverflowError) as e:await i.followup.send(str(e),ephemeral=True)

async def handle(i):
 if i.type!=discord.InteractionType.component or not i.data.get('custom_id','').startswith('social:'):return False
 if i.guild_id!=GUILD_ID:
  await i.response.send_message('지정 서버에서 사용하세요',ephemeral=True);return True
 _,kind,rid,action,rev=i.data['custom_id'].split(':');revision=int(rev)
 if action=='raise' or (kind=='lottery' and action=='numbers') or (kind=='crash' and action=='join'):
  await i.response.send_modal(InputModal(kind,rid,action,revision));return True
 private=action in ('cards','tickets','auto');await i.response.defer(ephemeral=private)
 try:
  if action=='cards':
   s=await asyncio.to_thread(social.read,kind,rid,str(i.user.id));p=next((p for p in s['players'] if p['uid']==str(i.user.id)),None)
   await i.followup.send('내 카드: '+' '.join(p['cards']) if p else '이 테이블의 참가자가 아닙니다.',ephemeral=True);return True
  if action=='tickets':
   with core.db() as c:
    rows=c.execute('SELECT numbers,payout,price FROM lottery_tickets WHERE draw=? AND uid=?',(rid,str(i.user.id))).fetchall()
    draw=c.execute("SELECT state FROM live_games WHERE id=? AND kind='lottery'",(rid,)).fetchone()
   fee=json.loads(draw[0]).get('fee',0) if draw else 0
   await i.followup.send(('\n'.join(f"{r['numbers']} · 💰 수익 {r['payout']-r['price']:+,} 띵조코인 (수수료 {fee}%)" for r in rows)[:1700] or '구매한 복권이 없어요.')+'\n'+balance_text(str(i.user.id)),ephemeral=True);return True
  if kind=='lottery' and action=='auto':
   r=await op(i,'lottery/buy',dict(draw=rid));await i.followup.send('구매 번호: '+str(r['tickets'][0]['numbers']),ephemeral=True);return True
  if action=='refresh':s=await asyncio.to_thread(social.read,kind,rid)
  elif kind=='holdem':s=await op(i,'holdem/'+(action if action in ('join','start','leave') else 'action'),dict(table=rid,revision=revision,action=action))
  elif kind=='crash':s=await op(i,'crash/cashout',dict(round=rid))
  else:raise ValueError('잘못된 게임 요청')
  await update_message(i,s)
 except (ValueError,PermissionError) as e:await i.followup.send(str(e),ephemeral=True)
 return True

@tasks.loop(seconds=3)
async def live_updates():
 if not CLIENT or not CLIENT.is_ready():return
 try:
  await asyncio.to_thread(core.maintenance)
  with core.db() as c:rows=c.execute("SELECT * FROM live_games WHERE message IS NOT NULL AND (status IN ('lobby','active','open','flying') OR created>?) ORDER BY created DESC LIMIT 40",(time.time()-86400,)).fetchall()
  for row in rows:
   s=json.loads(row['state']);public=social.public(s);finger='display-v2:'+json.dumps(public,sort_keys=True)
   # Lotteries/tables only edit on changes; crash display updates every 3s.
   key='live-view:'+row['id']
   with core.db() as c:old=c.execute('SELECT value FROM meta WHERE key=?',(key,)).fetchone()
   if old and old[0]==finger:continue
   ch=CLIENT.get_channel(int(row['channel']))
   if not ch:continue
   try:await ch.get_partial_message(int(row['message'])).edit(embed=embed(public),view=view(public),allowed_mentions=discord.AllowedMentions.none())
   except discord.NotFound:
    with core.db(True) as c:c.execute('UPDATE live_games SET message=NULL WHERE id=?',(row['id'],))
    continue
   except discord.HTTPException:continue
   with core.db(True) as c:c.execute('INSERT INTO meta VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,finger))
 except Exception as e:
  with core.db(True) as c:core.audit(c,'bot','live-game-error',dict(type=type(e).__name__))

async def announce(guild,p):
 if not p.get('channel'):return
 ch=guild.get_channel_or_thread(int(p['channel']))
 if ch:
  s=await asyncio.to_thread(social.read,p['kind'],p['id']);await ch.send(embed=embed(s),view=view(s),allowed_mentions=discord.AllowedMentions.none())

def register(client,tree,guild_id):
 global CLIENT,GUILD_ID
 CLIENT=client;GUILD_ID=guild_id
 @tree.command(name='홀덤',description='2~6명이 참여하는 텍사스 홀덤 테이블을 만들어요')
 async def holdem(i:discord.Interaction,바이인:app_commands.Range[int,20]=1000,빅블라인드:app_commands.Range[int,2]=20):
  await i.response.defer();s=await op(i,'holdem/create',dict(buyin=바이인,blind=빅블라인드));await publish(i,s)
 @tree.command(name='홀덤보기',description='테이블을 다시 표시하고 내 카드를 확인해요')
 async def holdem_show(i:discord.Interaction,테이블:str=''):
  if i.guild_id!=GUILD_ID:raise ValueError('지정 서버에서 사용하세요')
  await i.response.defer()
  if not 테이블:
   with core.db() as c:row=c.execute("SELECT id FROM live_games WHERE kind='holdem' AND channel=? ORDER BY created DESC LIMIT 1",(str(i.channel_id),)).fetchone()
   if not row:return await i.followup.send('이 채널에는 홀덤 테이블이 없어요.',ephemeral=True)
   테이블=row['id']
  s=await asyncio.to_thread(social.read,'holdem',테이블)
  await publish(i,s)
 @tree.command(name='복권',description='현재 복권 회차와 구매 버튼을 표시해요')
 async def lottery(i:discord.Interaction):
  if i.guild_id!=GUILD_ID:raise ValueError('지정 서버에서 사용하세요')
  await i.response.defer();s=await asyncio.to_thread(social.read,'lottery')
  if not s:return await i.followup.send('복권 판매가 비활성화되어 있어요.',ephemeral=True)
  await publish(i,s)
 @tree.command(name='크래시',description='크래시에 베팅해요. 자동정산 0은 수동 정산입니다')
 async def crash(i:discord.Interaction,베팅:app_commands.Range[int,1],자동정산:app_commands.Range[float,0.0,99.99]=2.0):
  await i.response.defer();s=await op(i,'crash/join',dict(bet=베팅,auto=round(자동정산*100)));await publish(i,s)
 @tree.command(name='크래시보기',description='현재 채널의 크래시 화면을 다시 표시해요')
 async def crash_show(i:discord.Interaction):
  if i.guild_id!=GUILD_ID:raise ValueError('지정 서버에서 사용하세요')
  await i.response.defer()
  with core.db() as c:r=c.execute("SELECT id FROM live_games WHERE kind='crash' AND channel=? ORDER BY created DESC LIMIT 1",(str(i.channel_id),)).fetchone()
  if not r:return await i.followup.send('이 채널에는 크래시 기록이 없어요.',ephemeral=True)
  await publish(i,await asyncio.to_thread(social.read,'crash',r['id']))
