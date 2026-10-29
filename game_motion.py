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

async def reveal(edit,r,final_embed,final_view):
 try:
  for frame in frames(r['game']):
   e=discord.Embed(title=games.CATALOG[r['game']][0],description=frame,color=0x9d85ff)
   e.set_footer(text='결과 공개 연출 · 표시되는 중간 그림은 실제 결과가 아닙니다')
   await edit(embed=e,view=discord.ui.View(timeout=None))
   await asyncio.sleep(DURATION[r['game']]/len(frames(r['game'])))
 except discord.HTTPException:
  pass
 finally:
  await edit(embed=final_embed,view=final_view)
