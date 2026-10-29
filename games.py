"""Persistable casino rules. Only public_view may cross the API boundary."""
import math
import secrets

RNG = secrets.SystemRandom()
CATALOG = {
 'coin': ('홀짝', '주사위 홀/짝을 맞히면 원금 포함 2배', False),
 'dice': ('주사위', '1~6 중 선택한 숫자가 나오면 6배', False),
 'baskin': ('배스킨31', '1~3개씩 숫자를 세고 31을 말하면 패배. 봇은 무작위 선택. 승리 2배', True),
 'scratch': ('스크래치', '세 칸 일치 확률 1/16, 일치 시 16배', False),
 'slots': ('슬롯', '세 릴 일치 확률 1/25, 일치 시 25배', False),
 'wheel': ('돌림판', '8칸: 0·0·0·0·1·1·2·4배', False),
 'mines': ('지뢰찾기', '9칸 중 지뢰 3개. 안전한 칸을 열고 정산 가능', True),
 'highlow': ('하이로우', '독립적인 1~13 카드. 높음/낮음 선택, 동점은 패배. 확률에 반비례한 배당', True),
 'blackjack': ('블랙잭', '6덱, 딜러 소프트17 스탠드. 승리 2배, 자연 블랙잭 2.5배, 무승부 원금', True),
 'roulette': ('룰렛', '유럽식 0~36. 빨강/검정 2배, 0 선택 36배', False),
 'indian': ('인디언 포커', '상대 카드만 보고 콜 또는 폴드. 높은 카드 승리 2배, 동점 원금, 폴드 반액 반환', True),
 'ttt': ('틱택토', '무작위 봇과 대결. 승리 2배, 무승부 원금', True),
 'bomb': ('폭탄', '5개 전선 중 폭탄 1개. 성공할 때마다 정산 가능', True),
 'tower': ('타워', '층마다 3칸 중 안전한 칸 2개. 최대 6층, 정산 가능', True),
 'horse': ('경마', '동일한 확률의 말 5마리. 선택한 말이 우승하면 5배', False),
}
RED = {1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36}

def number(value, lo, hi):
 if type(value) is not int or not lo <= value <= hi: raise ValueError(f'{lo}~{hi} 사이 정수를 선택하세요')
 return value

def total(cards):
 value=sum(min(c,10) if c!=1 else 11 for c in cards)
 for c in cards:
  if value>21 and c==1:value-=10
 return value

def finish(s,mult,message):
 s.update(done=True,mult=mult,message=message)
 return s

def start(game, choice=None):
 if game not in CATALOG:raise ValueError('지원하지 않는 게임')
 s=dict(game=game,done=False,mult=0,message='',step=0)
 if game=='coin':
  if choice not in ('odd','even'):raise ValueError('odd 또는 even을 선택하세요')
  roll=RNG.randint(1,6);s['roll']=roll
  finish(s,2 if (roll%2==1)==(choice=='odd') else 0,f'주사위: {roll}')
 elif game=='dice':
  number(choice,1,6);roll=RNG.randint(1,6);s['roll']=roll;finish(s,6 if roll==choice else 0,f'주사위: {roll}')
 elif game in ('slots','scratch'):
  n=5 if game=='slots' else 4;s['symbols']=[RNG.randrange(n) for _ in range(3)]
  finish(s,n*n if len(set(s['symbols']))==1 else 0,'세 칸 일치!' if len(set(s['symbols']))==1 else '다음 기회에')
 elif game=='wheel':
  s['segment']=RNG.randrange(8);m=[0,0,0,0,1,1,2,4][s['segment']];finish(s,m,f'{m}배 칸에 멈췄어요')
 elif game=='roulette':
  if choice not in ('red','black','zero'):raise ValueError('red, black, zero 중 선택하세요')
  r=RNG.randrange(37);s['roll']=r;color='zero' if r==0 else 'red' if r in RED else 'black';finish(s,(36 if r==0 else 2) if choice==color else 0,f'{r} · {color}')
 elif game=='horse':
  number(choice,1,5);s['order']=RNG.sample(list(range(1,6)),5);finish(s,5 if s['order'][0]==choice else 0,f"{s['order'][0]}번 말 우승")
 elif game=='blackjack':
  deck=list(range(1,14))*24;RNG.shuffle(deck);s.update(deck=deck,player=[deck.pop(),deck.pop()],dealer=[deck.pop(),deck.pop()])
  p,d=total(s['player']),total(s['dealer'])
  if p==21 or d==21:finish(s,1 if p==d else 2.5 if p==21 else 0,'자연 블랙잭 판정')
 elif game=='mines':s.update(hazards=RNG.sample(list(range(9)),3),opened=[],mult=1)
 elif game=='bomb':s.update(hazards=[RNG.randrange(5)],opened=[],mult=1)
 elif game=='tower':s.update(hazards=[RNG.randrange(3) for _ in range(6)],opened=[],mult=1)
 elif game=='highlow':s.update(card=RNG.randint(1,13),mult=1)
 elif game=='baskin':s.update(count=0)
 elif game=='indian':s.update(player=RNG.randint(1,13),dealer=RNG.randint(1,13))
 elif game=='ttt':s.update(board=['']*9)
 return s

def action(s, act, value=None):
 if s['done']:raise ValueError('이미 종료된 게임입니다')
 g=s['game']
 if act=='cashout' and g in ('mines','bomb','tower','highlow'):
  if s['step']<1:raise ValueError('한 번 이상 진행한 뒤 정산할 수 있어요')
  return finish(s,s['mult'],'정산 완료')
 if g in ('mines','bomb') and act=='pick':
  n=9 if g=='mines' else 5;h=3 if g=='mines' else 1;number(value,0,n-1)
  if value in s['opened']:raise ValueError('이미 선택한 칸입니다')
  s['opened'].append(value)
  if value in s['hazards']:return finish(s,0,'폭탄!')
  s['step']+=1;k=s['step'];s['mult']=math.comb(n,k)/math.comb(n-h,k)
  if k==n-h:finish(s,s['mult'],'모든 안전한 칸 발견!')
 elif g=='tower' and act=='pick':
  number(value,0,2);s['opened'].append(value)
  if s['hazards'][s['step']]==value:return finish(s,0,'탑에서 떨어졌어요')
  s['step']+=1;s['mult']=1.5**s['step']
  if s['step']==6:finish(s,s['mult'],'정상 도착!')
 elif g=='highlow' and act in ('higher','lower'):
  prev=s['card'];ways=(13-prev) if act=='higher' else (prev-1)
  if ways==0:raise ValueError('나올 수 없는 방향입니다')
  new=RNG.randint(1,13);s['card']=new;s['previous']=prev;s['step']+=1
  if not (new>prev if act=='higher' else new<prev):return finish(s,0,'예측 실패 (동점 포함)')
  s['mult']*=13/ways
  if s['step']==5:finish(s,s['mult'],'5연속 성공!')
 elif g=='blackjack' and act in ('hit','stand'):
  if act=='hit':
   s['player'].append(s['deck'].pop())
   if total(s['player'])>21:return finish(s,0,'플레이어 버스트')
   if total(s['player'])<21:return s
  while total(s['dealer'])<17:s['dealer'].append(s['deck'].pop())
  p,d=total(s['player']),total(s['dealer']);finish(s,2 if d>21 or p>d else 1 if p==d else 0,f'플레이어 {p} / 딜러 {d}')
 elif g=='baskin' and act=='count':
  number(value,1,3);s['count']+=value
  if s['count']>=31:return finish(s,0,'31을 말해서 패배했어요')
  bot=RNG.randint(1,min(3,31-s['count']));s['count']+=bot;s['botCount']=bot
  if s['count']>=31:finish(s,2,'봇이 31을 말했어요!')
 elif g=='indian' and act in ('call','fold'):
  p,d=s['player'],s['dealer'];finish(s,0.5 if act=='fold' else 2 if p>d else 1 if p==d else 0,f'내 카드 {p} / 상대 {d}')
 elif g=='ttt' and act=='pick':
  number(value,0,8);b=s['board']
  if b[value]:raise ValueError('이미 채워진 칸입니다')
  b[value]='X'
  def winner(symbol):return any(all(b[i]==symbol for i in line) for line in [(0,1,2),(3,4,5),(6,7,8),(0,3,6),(1,4,7),(2,5,8),(0,4,8),(2,4,6)])
  if winner('X'):return finish(s,2,'승리!')
  empty=[i for i,x in enumerate(b) if not x]
  if not empty:return finish(s,1,'무승부')
  b[RNG.choice(empty)]='O'
  if winner('O'):finish(s,0,'봇 승리')
  elif all(b):finish(s,1,'무승부')
 else:raise ValueError('이 게임에서 사용할 수 없는 동작입니다')
 return s

def public_view(s):
 out={k:v for k,v in s.items() if k not in ('hazards','deck')}
 if not s['done']:
  if s['game']=='blackjack':out['dealer']=[s['dealer'][0],None]
  if s['game']=='indian':out['player']=None
 elif 'hazards' in s:out['hazards']=s['hazards']
 return out
