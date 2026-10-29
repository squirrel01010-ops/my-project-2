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
 if game in ('wheel','roulette'):return ['🎡 회전 시작\n\n🔴 ⚫ 🟢 🔴 ⚫\n⬆️','🎡 빙글빙글…\n\n⚫ 🔴 ⚫ 🟢 🔴\n　　 ⬆️','🎡 천천히 멈추는 중…\n\n🟢 ⚫ 🔴 ⚫ 🔴\n　　　　 ⬆️']
 if game=='scratch':return ['🎟️ 스크래치\n\n⬜ ⬜ ⬜','🪙 긁는 중…\n\n✨ ⬜ ⬜','🪙 마지막 칸 확인 중…\n\n✨ ✨ ⬜']
 if game in ('blackjack','highlow','indian'):return ['🃏 카드를 섞는 중…\n\n🂠 🂠 🂠','🃏 카드 이동 중…\n\n🂠 ➡️ 🂠','🃏 카드를 펼치는 중…\n\n🂠 ✨']
 if game=='mines':return ['⛏️ 땅을 파는 중…\n\n🟫 🟫 🟫','⛏️ 조심조심…\n\n🟫 ✨ 🟫','🔎 칸 확인 중…']
 if game=='bomb':return ['💣 전선을 고르는 중…\n\n🟥 🟦 🟨 🟩 🟪','✂️ 전선 절단 중…','💣 ··· 결과 확인 중…']
 if game=='tower':return ['🗼 다음 층으로…\n\n⬜ ⬜ ⬜','🧗 올라가는 중…\n\n　⬆️','🗼 발판 확인 중…']
 if game=='ttt':return ['⭕ ❌ ⬜\n⬜ ⬜ ⬜\n⬜ ⬜ ⬜\n\n수를 두는 중…','🤔 상대가 생각 중…','⭕ ❌ 다음 수 확인 중…']
 return ['🔢 숫자를 세는 중…','🔢 1 · 2 · 3 …','🤔 상대의 선택 확인 중…']

WHEEL_LABELS=['💀 꽝','💀 꽝','💀 꽝','💀 꽝','🪙 ×1','🪙 ×1','⭐ ×2','🌟 ×4']
def wheel_board(index,multipliers=None):
 labels=WHEEL_LABELS if multipliers is None else [('💀 꽝' if m==0 else f'🪙 ×{m:g}') for m in multipliers]
 return '\n'.join(('➜ **'+label+'**' if n==index else '　'+label) for n,label in enumerate(labels))

def sequence(r):
 game=r['game']
 if game=='wheel':
  target=r.get('state',{}).get('segment',0)
  positions=[(target-offset)%8 for offset in (19,16,13,10,7,5,3,1,0)]
  delays=[.5,.6,.7,.8,1,1.2,1.4,1.7,2.1]
  return [(wheel_board(index,r.get('state',{}).get('wheelMultipliers')),delay) for index,delay in zip(positions,delays)]
 return [(frame,DURATION[game]/len(frames(game))) for frame in frames(game)]

async def reveal(edit,r,final_embed,final_view):
 try:
  for frame,delay in sequence(r):
   e=discord.Embed(title=('🎡 돌림판이 돌아가고 있어요…' if r['game']=='wheel' else games.CATALOG[r['game']][0]+' 진행 중…'),description=(f"👤 {r.get('display_name','참가자')} · 🪙 {r.get('bet',0):,} EXP\n\n"+frame),color=0xf1c40f)
   e.set_footer(text='행운을 빌어요!')
   await edit(embed=e,view=discord.ui.View(timeout=None))
   await asyncio.sleep(delay)
 except discord.HTTPException:
  pass
 finally:
  await edit(embed=final_embed,view=final_view)
