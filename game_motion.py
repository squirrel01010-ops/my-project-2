"""Cosmetic Discord frames: never roll, bet, or settle here."""
import asyncio
import discord
import games

BUSY=set()
DURATION=dict(coin=6,dice=7,baskin=6,scratch=9,slots=8,wheel=10,mines=6,highlow=7,blackjack=8,roulette=10,indian=8,ttt=6,bomb=9,tower=7,horse=12)

def frames(game):
 return ['🎡 회전 시작\n\n🔴 ⚫ 🟢 🔴 ⚫\n⬆️','🎡 빙글빙글…\n\n⚫ 🔴 ⚫ 🟢 🔴\n　　 ⬆️','🎡 천천히 멈추는 중…\n\n🟢 ⚫ 🔴 ⚫ 🔴\n　　　　 ⬆️']

WHEEL_LABELS=['💀 꽝','💀 꽝','💀 꽝','💀 꽝','🪙 ×1','🪙 ×1','⭐ ×2','🌟 ×4']
def wheel_board(index,multipliers=None):
 labels=WHEEL_LABELS if multipliers is None else [('💀 꽝' if m==0 else f'🪙 ×{m:g}') for m in multipliers]
 return '\n'.join(('➜ **'+label+'**' if n==index else '　'+label) for n,label in enumerate(labels))

SYMBOLS=['🍒','🍋','🔔','⭐','💎']
def card(n):return '▧' if n is None else str({1:'A',11:'J',12:'Q',13:'K'}.get(n,n))
def box(text):return '```\n'+text+'\n```'
def cards(values):return '  '.join('['+card(n)+']' for n in values)

def grid(cells,width=3):
 return box('\n'.join('  '.join(cells[n:n+width]) for n in range(0,len(cells),width)))

def board(r):
 g=r['game'];s=r.get('state',{});done=r.get('status')=='done'
 if g in ('slots','scratch'):return '　│　'.join(SYMBOLS[n] for n in s.get('symbols',[0,1,2]))
 if g in ('coin','dice'):
  roll=s.get('roll',1);return box('       '+ '⚀⚁⚂⚃⚄⚅'[roll-1]+f'\n\n       {roll}'+(' · 홀수' if roll%2 else ' · 짝수'))
 if g=='horse':return '\n'.join(f'**{i+1}위**　{n}번 말' for i,n in enumerate(s.get('order',[])))
 if g=='blackjack':return box('DEALER   '+cards(s.get('dealer',[None,None]))+'\n\nPLAYER   '+cards(s.get('player',[None,None])))
 if g=='indian':return box('상대     '+cards([s.get('dealer')])+'\n\n나       '+cards([s.get('player')]))
 if g=='highlow':return box(('이전  ['+card(s['previous'])+']    →    ' if 'previous' in s else '')+'현재  ['+card(s.get('card'))+']')
 if g=='baskin':
  count=s.get('count',0);return box(f'현재 숫자     {count} / 31\n\n'+''.join('■' if n<count else '·' for n in range(31)))
 if g=='ttt':return grid([v or str(n+1) for n,v in enumerate(s.get('board',['']*9))])
 if g in ('mines','bomb'):
  opened=s.get('opened',[]);hazards=s.get('hazards',[]) if done else []
  cells=[('×' if n in hazards else '◆' if n in opened else str(n+1)) for n in range(9 if g=='mines' else 5)]
  return grid(cells,3 if g=='mines' else 5)
 if g=='tower':
  step=s.get('step',0);return box('\n'.join(f'{n+1}층  '+('  ◆  ' if n<step else '[1] [2] [3]')+('  ◀ 현재' if n==step and step<6 else '') for n in reversed(range(6))))
 return ''

def sequence(r):
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
  elif game=='horse':
   order=s.get('order',[1,2,3,4,5]);lines=[]
   for n in range(1,6):
    rank=order.index(n);pos=min(12,max(0,int(progress*(12-rank))+(0 if t==7 else ((t+n)%3-1))))
    lines.append(str(n)+'  '+ '─'*pos+'▶'+'·'*(12-pos)+'┃')
   text=box('START                 FINISH\n\n'+'\n'.join(lines))+'\n'+('결승선 통과' if t==7 else f'경주 진행  {int(progress*100)}%')
  elif game in ('blackjack','indian','highlow'):
   if game=='blackjack':
    player=s.get('player',[None,None]);dealer=s.get('dealer',[None,None]);visible=max(0,t-1)
    text=box('DEALER   '+cards([v if n<max(0,visible-len(player)) else None for n,v in enumerate(dealer)])+'\n\nPLAYER   '+cards([v if n<visible else None for n,v in enumerate(player)]))
   elif game=='indian':text=box('상대     '+cards([s.get('dealer') if t>2 else None])+'\n\n나       '+cards([s.get('player') if t==7 else None]))
   else:text=box('이전    ['+card(s.get('previous',s.get('card')))+']     →     ['+card(s.get('card') if t==7 else None)+']')
   if t==7:text=board(r)
   text+='\n카드 공개 중'
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

async def reveal(edit,r,final_embed,final_view):
 try:
  for frame,delay in sequence(r):
   e=discord.Embed(title=('🎡 돌림판이 돌아가고 있어요…' if r['game']=='wheel' else games.CATALOG[r['game']][0]),description=(f"👤 {r.get('display_name','참가자')} · 🪙 {r.get('bet',0):,} EXP\n\n"+frame),color=0xf1c40f if r['game'] in ('wheel','roulette') else 0x7289da)
   if r['game'] not in ('wheel','roulette'):
    e.title=games.CATALOG[r['game']][0];e.description=frame
    e.set_footer(text=f"{r.get('display_name','참가자')} · 베팅 {r.get('bet',0):,} EXP")
   else:e.set_footer(text='행운을 빌어요!')
   await edit(embed=e,view=discord.ui.View(timeout=None))
   await asyncio.sleep(delay)
 except discord.HTTPException:
  pass
 finally:
  await edit(embed=final_embed,view=final_view)

