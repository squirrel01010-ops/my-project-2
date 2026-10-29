"""Cosmetic Discord frames: never roll, bet, or settle here."""
import asyncio
import discord
import games

BUSY=set()
DURATION=dict(coin=6,dice=7,baskin=6,scratch=9,slots=8,wheel=10,mines=6,highlow=7,blackjack=8,roulette=10,indian=8,ttt=6,bomb=9,tower=7,horse=12)

def frames(game):
 if game=='slots':return ['🎰 슬롯 회전 중\n\n🍒 │ 🔔 │ 🍋','🎰 슬롯 회전 중\n\n🍇 │ 🍒 │ 🔔','🎰 마지막 릴이 멈추는 중…\n\n🍇 │ 🔔 │ ❔']
 if game in ('coin','dice'):return ['🎲 데굴…\n\n⚀ ⤴','🎲 데구르르…\n\n⤵ ⚄','🎲 주사위가 멈추는 중…\n\n❔']
 if game=='horse':return ['🏁 경주 시작!\n① 🐎 ▫▫▫▫▫\n② 🐎 ▫▫▫▫▫\n③ 🐎 ▫▫▫▫▫\n④ 🐎 ▫▫▫▫▫\n⑤ 🐎 ▫▫▫▫▫','🏇 달리는 중…\n① ▫🐎 ▫▫▫▫\n② ▫▫🐎 ▫▫▫\n③ ▫🐎 ▫▫▫▫\n④ ▫▫🐎 ▫▫▫\n⑤ ▫🐎 ▫▫▫▫','🏁 결승선 앞!\n\n🏇 💨 🏇 💨 🏇\n\n최종 순위 확인 중…']
 if game in ('wheel','roulette'):return ['🎡 회전 시작\n\n💨 0배 · 🪙 1배 · 💎 2배 · 👑 4배' if game=='wheel' else '🎡 회전 시작\n\n💨 0배 · 💎 2배 · 🌟 36배','🎡 빙글빙글…\n\n✨ ✨ ✨','🎡 천천히 멈추는 중…\n\n결과 확인 중…']
 if game=='scratch':return ['🎟️ 스크래치\n\n⬜ ⬜ ⬜','🪙 긁는 중…\n\n✨ ⬜ ⬜','🪙 마지막 칸 확인 중…\n\n✨ ✨ ⬜']
 if game in ('blackjack','highlow','indian'):return ['🃏 카드를 섞는 중…\n\n🂠 🂠 🂠','🃏 카드 이동 중…\n\n🂠 ➡️ 🂠','🃏 카드를 펼치는 중…\n\n🂠 ✨']
 if game=='mines':return ['⛏️ 땅을 파는 중…\n\n🟫 🟫 🟫','⛏️ 조심조심…\n\n🟫 ✨ 🟫','🔎 칸 확인 중…']
 if game=='bomb':return ['💣 전선을 고르는 중…\n\n🟥 🟦 🟨 🟩 🟪','✂️ 전선 절단 중…','💣 ··· 결과 확인 중…']
 if game=='tower':return ['🗼 다음 층으로…\n\n⬜ ⬜ ⬜','🧗 올라가는 중…\n\n　⬆️','🗼 발판 확인 중…']
 if game=='ttt':return ['⭕ ❌ ⬜\n⬜ ⬜ ⬜\n⬜ ⬜ ⬜\n\n수를 두는 중…','🤔 상대가 생각 중…','⭕ ❌ 다음 수 확인 중…']
 return ['🔢 숫자를 세는 중…','🔢 1 · 2 · 3 …','🤔 상대의 선택 확인 중…']

SYMBOLS=['🍒','🍋','🔔','⭐','💎']
def card(n):return '▧' if n is None else str({1:'A',11:'J',12:'Q',13:'K'}.get(n,n))
def box(text):return '```\n'+text+'\n```'
def cards(values):return '  '.join('['+card(n)+']' for n in values)
def card_table(values):
 values=list(values);rows=[]
 for offset in range(0,len(values),5):
  hand=values[offset:offset+5]
  rows.extend([' '.join('┌────┐' for _ in hand),' '.join('│'+card(n).center(4)+'│' for n in hand),' '.join('└────┘' for _ in hand)])
 return '\n'.join(rows)

HINTS={
 'blackjack':'카드를 더 받거나, 현재 합계로 멈추세요.',
 'indian':'상대 카드를 보고 콜 또는 폴드를 선택하세요.',
 'highlow':'다음 카드가 더 높을지, 낮을지 선택하세요.',
 'baskin':'한 번에 1~3개. 31을 말하면 패배해요.',
 'ttt':'내 표시는 X · 원하는 칸을 선택하세요.',
 'mines':'안전한 칸을 찾아보세요. 지뢰는 3개예요.',
 'bomb':'전선을 선택하세요. 5개 중 1개는 폭탄이에요.',
 'tower':'세 발판 중 하나를 선택하세요. 두 개가 안전해요.'}
def hint(r):
 text=HINTS.get(r['game'],'')
 if r['game'] in ('mines','bomb','tower','highlow') and r.get('state',{}).get('step',0)>0:text+='\n계속 도전하거나 지금 정산할 수 있어요.'
 return text


def grid(cells,width=3):
 return box('\n'.join('  '.join(cells[n:n+width]) for n in range(0,len(cells),width)))

RACE_LENGTH=24
RACE_TICKS=24

def horse_position(order,horse,tick):
 return min(RACE_LENGTH,max(0,tick)*RACE_LENGTH//(20+order.index(horse)))

def horse_track(order,tick):
 lines=[]
 for horse in range(1,6):
  pos=horse_position(order,horse,tick)
  lines.append(f'{horse} 🏁'+ '·'*(RACE_LENGTH-pos)+'🐎'+'·'*pos+'┃')
 return box('FINISH ← START\n\n'+'\n'.join(lines))

def board(r):
 g=r['game'];s=r.get('state',{});done=r.get('status')=='done'
 if g in ('slots','scratch'):return '　│　'.join(SYMBOLS[n] for n in s.get('symbols',[0,1,2]))
 if g in ('coin','dice'):
  roll=s.get('roll',1);return box('       '+ '⚀⚁⚂⚃⚄⚅'[roll-1]+f'\n\n       {roll}'+(' · 홀수' if roll%2 else ' · 짝수'))
 if g=='horse':return horse_track(s.get('order',[1,2,3,4,5]),RACE_TICKS)+'\n'+'\n'.join(f'**{i+1}위**　{n}번 🐎' for i,n in enumerate(s.get('order',[])))
 if g=='blackjack':return box('DEALER\n'+card_table(s.get('dealer',[None,None]))+'\n\nPLAYER · '+str(games.total([n for n in s.get('player',[]) if n is not None]))+'\n'+card_table(s.get('player',[None,None])))
 if g=='indian':return box('상대 카드\n'+card_table([s.get('dealer')])+'\n\n내 카드\n'+card_table([s.get('player')]))
 if g=='highlow':return box(('이전  '+card(s['previous'])+'  →  ' if 'previous' in s else '')+'현재 카드\n'+card_table([s.get('card')]))
 if g=='baskin':
  count=s.get('count',0);return box(f'현재 숫자     {count} / 31\n\n'+''.join('■' if n<count else '·' for n in range(31)))
 if g=='ttt':return grid([v or str(n+1) for n,v in enumerate(s.get('board',['']*9))])
 if g in ('mines','bomb'):
  opened=s.get('opened',[]);hazards=s.get('hazards',[]) if done else []
  cells=[('×' if n in hazards else '◆' if n in opened else str(n+1)) for n in range(9 if g=='mines' else 5)]
  return grid(['['+v+']' for v in cells],3 if g=='mines' else 5)
 if g=='tower':
  step=s.get('step',0);return box('\n'.join(f'{n+1}층  '+('  ◆  ' if n<step else '[1] [2] [3]')+('  ◀ 현재' if n==step and step<6 else '') for n in reversed(range(6))))
 return ''


def staged_sequence(r):
 game=r['game'];s=r.get('state',{})
 if games.CATALOG[game][2] and 'previous_state' not in r:return []
 if game=='wheel':
  target=s.get('segment',0);positions=[(target-offset)%8 for offset in (19,16,13,10,7,5,3,1,0)]
  return [(wheel_board(index,s.get('wheelMultipliers')),delay) for index,delay in zip(positions,[.5,.6,.7,.8,1,1.2,1.4,1.7,2.1])]
 if game=='roulette':return [(frame,DURATION[game]/len(frames(game))) for frame in frames(game)]
 out=[];steps=8
 for t in range(steps):
  progress=(t+1)/steps
  if game=='slots':
   actual=s.get('symbols',[0,1,2]);locked=max(0,t-4)
   reels=[SYMBOLS[actual[n]] if n<locked else SYMBOLS[(t*(n+1)+n)%5] for n in range(3)]
   if t==7:reels=[SYMBOLS[n] for n in actual]
   text='　│　'.join(reels)+'\n\n'+('**'+str(min(3,locked))+' / 3 릴 정지**' if t<7 else '**회전 완료**')
  elif game=='scratch':
   actual=s.get('symbols',[0,1,2]);opened=min(3,t//2)
   text='　│　'.join(SYMBOLS[actual[n]] if n<opened else '▧' for n in range(3))+'\n\n'+('마지막 칸을 긁고 있어요' if opened==2 else '스크래치를 긁고 있어요')
   if t==7:text='　│　'.join(SYMBOLS[n] for n in actual)
  elif game in ('coin','dice'):
   face=s.get('roll',1) if t==7 else (t*3+t//2)%6+1
   text=box(' '*((t%3)*3+2)+'⚀⚁⚂⚃⚄⚅'[face-1]+('\n'+ ' '*((t%3)*3+2)+'╱' if t<5 else ''))+'\n'+('주사위가 멈췄어요' if t==7 else '주사위 굴리는 중')
  elif game in ('blackjack','indian','highlow'):
   if game=='blackjack':
    player=s.get('player',[None,None]);dealer=s.get('dealer',[None,None]);previous=r.get('previous_state',{});visible=max(len(previous.get('player',[])),t-1)
    text=box('DEALER   '+cards([v if n<max(0,visible-len(player)) else None for n,v in enumerate(dealer)])+'\n\nPLAYER   '+cards([v if n<visible else None for n,v in enumerate(player)]))
   elif game=='indian':text=box('상대     '+cards([s.get('dealer') if t>2 else None])+'\n\n나       '+cards([s.get('player') if t==7 else None]))
   else:text=box('이전    ['+card(s.get('previous',s.get('card')))+']     →     ['+card(s.get('card') if t==7 else None)+']')
   if t==7:text=board(r)
   else:text+='\n카드 공개 중'
  elif game in ('mines','bomb'):
   opened=s.get('opened',[]);last=opened[-1] if opened else 0;total=9 if game=='mines' else 5
   cells=[('◆' if n in opened[:-1] else ('◇' if t%2==0 else '·') if n==last else str(n+1)) for n in range(total)]
   text=grid(cells,3 if game=='mines' else 5)+'\n'+(f'{last+1}번 칸 확인 중' if game=='mines' else f'{last+1}번 전선 절단 중')
   if t==7:text=board(r)
  elif game=='tower':
   step=s.get('step',0);current=max(0,step-1);cells=[]
   for n in reversed(range(6)):
    cells.append(f'{n+1}층  '+('  ◆  ' if n<current else '  ◇  ' if n==current and t%2==0 else '[1] [2] [3]'))
   text=box('\n'.join(cells))+'\n다음 발판으로 이동 중'
   if t==7:text=board(r)
  elif game=='ttt':
   cells=s.get('board',['']*9);previous=r.get('previous_state',{}).get('board',['']*9)
   changes=sorted([n for n in range(9) if cells[n]!=previous[n]],key=lambda n:cells[n]!='X')
   shown=changes[:(1 if t>2 else 0)+(1 if t==7 else 0)]
   text=grid([cells[n] if n in shown else previous[n] or str(n+1) for n in range(9)])+'\n'+('상대가 수를 두고 있어요' if t>3 else '내 차례')
  else:
   end=s.get('count',0);value=max(0,end-5)+int(min(5,end)*progress)
   text=box(f'현재 숫자     {value} / 31\n\n'+''.join('■' if n<value else '·' for n in range(31)))+'\n숫자를 세는 중'
  out.append((text,1))
 weights=[.75,.75,.85,.95,1,1.1,1.25,1.35];total=sum(weights)
 return [(text,DURATION[game]*weights[n]/total) for n,(text,_) in enumerate(out)]


ROULETTE_RING=[0,32,15,19,4,21,2,25,17,34,6,27,13,36,11,30,8,23,10,5,24,16,33,1,20,14,31,9,22,18,29,7,28,12,35,3,26]
SPIN_DELAYS=[.5,.5,.6,.6,.7,.8,.9,1,1.2,1.4,1.7,2,2.4]
def spin_frame(r,index):
 if r['game']=='wheel':
  payouts=r.get('state',{}).get('wheelMultipliers',[0,0,0,0,1,1,2,4])
  return '\n'.join(('➜ **' if n==index else '　')+f'×{m:g}'+('**' if n==index else '') for n,m in enumerate(payouts))
 rows=[]
 for offset in range(-2,3):
  n=ROULETTE_RING[(index+offset)%37];color='🟢' if n==0 else '🔴' if n in games.RED else '⚫'
  rows.append(('➜ **' if offset==0 else '　')+f'{color} {n:02d}'+('**' if offset==0 else ''))
 return '\n'.join(rows)
def card_sequence(r):
 import copy
 s=r.get('state',{});g=r['game'];prev=r.get('previous_state',{})
 view=copy.deepcopy(r);v=view['state'];tasks=[]
 keys=('player','dealer') if g=='blackjack' else ('dealer','player') if g=='indian' else ('card',)
 for key in keys:
  final=s.get(key,[] if g=='blackjack' else None)
  if isinstance(final,list):
   known=prev.get(key,[]);v[key]=[known[i] if i<len(known) else None for i in range(len(final))]
   for i,n in enumerate(final):
    if n is not None and (i>=len(known) or known[i]!=n):tasks.append((key,i,n))
  else:
   v[key]=None
   if final is not None:tasks.append((key,None,final))
 out=[board(view)]
 for key,i,n in tasks:
  if i is None:v[key]=n
  else:v[key][i]=n
  # Hidden dealer cards stay hidden until their turn to be revealed.
  out.append(board(view))
 out.append(board(r))
 return [(frame,DURATION[g]/len(out)) for frame in out]

def sequence(r):
 if r['game']=='horse':
  order=r.get('state',{}).get('order',[1,2,3,4,5])
  return [(horse_track(order,tick),DURATION['horse']/(RACE_TICKS+1)) for tick in range(RACE_TICKS+1)]+[(board(r),1)]
 if r['game'] in ('blackjack','indian','highlow') and 'previous_state' in r:return card_sequence(r)
 if r['game'] not in ('wheel','roulette'):
  out=staged_sequence(r)
  if out:out[-1]=(board(r),out[-1][1])
  return out
 state=r.get('state',{});size=8 if r['game']=='wheel' else 37
 target=state.get('segment',0) if r['game']=='wheel' else ROULETTE_RING.index(state.get('roll',0))
 return [(spin_frame(r,(target-(len(SPIN_DELAYS)-1-i))%size),delay) for i,delay in enumerate(SPIN_DELAYS)]

async def reveal(edit,r,final_embed,final_view):
 try:
  for frame,delay in sequence(r):
   e=discord.Embed(title=games.CATALOG[r['game']][0],description=frame,color=0x9d85ff)
   await edit(embed=e,view=discord.ui.View(timeout=None))
   await asyncio.sleep(delay)
 except discord.HTTPException:
  pass
 finally:
  await edit(embed=final_embed,view=final_view)
