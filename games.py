"""Persistable casino rules. Only public_view may cross the API boundary."""
import math
import secrets

RNG = secrets.SystemRandom()
CATALOG = {
 'baccarat': ('바카라','플레이어 2배 · 뱅커 1.95배 · 무승부 9배 · 무승부 시 양쪽 베팅 원금 반환',False),
 'coin': ('홀짝', '주사위 홀/짝을 맞히면 원금 포함 2배', False),
 'dice': ('주사위', '1~6 중 선택한 숫자가 나오면 6배', False),
 'baskin': ('배스킨31', '1~3개씩 숫자를 세고 31을 말하면 패배. 봇은 무작위 선택. 승리 2배', True),
 'scratch': ('스크래치', '세 칸 일치 시 16배 · 모양 비중은 서버 설정 적용', False),
 'slots': ('슬롯', '두 개 일치 또는 모양별 세 개 일치 배율 적용 · 모양 비중은 서버 설정 적용', False),
 'wheel': ('돌림판', '8칸: 0·0·0·0·1·1·2·4배', False),
 'mines': ('지뢰찾기', '9칸 중 지뢰 3개. 안전한 칸을 열고 정산 가능', True),
 'highlow': ('하이로우', '독립적인 1~13 카드. 높음/낮음 선택, 동점은 패배. 확률에 반비례한 배당', True),
 'blackjack': ('블랙잭', '6덱, 딜러 소프트17 스탠드. 승리 2배, 자연 블랙잭 2.5배, 무승부 원금', True),
 'roulette': ('룰렛', '유럽식 0~36. 빨강/검정 2배, 0 선택 36배', False),
 'indian': ('인디언 포커', '상대 카드만 보고 콜 또는 폴드. 높은 카드 승리 2배, 동점 원금, 폴드 반액 반환', True),
 'ttt': ('틱택토', '무작위 봇과 대결. 승리 2배, 무승부 원금', True),
 'bomb': ('폭탄', '5개 전선 중 폭탄 1개. 성공할 때마다 정산 가능', True),
 'tower': ('타워', '층마다 3칸 중 안전한 칸 2개. 최대 6층, 정산 가능', True),
 'horse': ('경마', '말 5마리 · 추첨 비중은 서버 설정 적용. 선택한 말이 우승하면 5배', False),
}
WHEEL_ICONS=['🍒','🍋','🍇','🍀','🔔','⭐','💎','👑']
def wheel_badge(mult,index):return f'{WHEEL_ICONS[index]} {mult:g}배'

MULTIPLIER_ICONS={0:'💨',1:'🪙',2:'💎',4:'👑',36:'🌟'}
def multiplier_badge(mult):return f"{MULTIPLIER_ICONS.get(mult,'✨')} {mult:g}배"

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

SLOT_SYMBOLS=['🍒','🍋','🔔','⭐','💎']
SLOT_TRIPLES=[5,10,15,25,40]

def slot_rules(config):
 triples=config.get('tripleMultipliers',SLOT_TRIPLES)
 return f"정확히 두 개 일치 {config.get('pairMultiplier',0.5):g}배 · 세 개 일치 "+' / '.join(f'{symbol} {mult:g}배' for symbol,mult in zip(SLOT_SYMBOLS,triples))+' · 모두 다름 0배 · 원금 포함, 수익 수수료 별도'

def start(game, choice=None, config=None):
 config=config or {}
 if game not in CATALOG:raise ValueError('지원하지 않는 게임')
 s=dict(game=game,done=False,mult=0,message='',step=0)
 w=config.get('outcomeWeights',[])
 if w:s['outcomeWeights']=list(w)
 def draw(n,offset=0):return odds.choose(RNG,list(range(offset,n+offset)),w) if w else RNG.randrange(n)+offset
 if game=='coin':
  if choice not in ('odd','even'):raise ValueError('odd 또는 even을 선택하세요')
  roll=draw(6,1) if w else RNG.randint(1,6);s['roll']=roll
  finish(s,2 if (roll%2==1)==(choice=='odd') else 0,f'주사위: {roll}')
 elif game=='dice':
  number(choice,1,6);roll=draw(6,1) if w else RNG.randint(1,6);s['roll']=roll;finish(s,6 if roll==choice else 0,f'주사위: {roll}')
 elif game=='baccarat':
  if choice not in ('player','banker','tie'):raise ValueError('플레이어·뱅커·무승부 중 선택하세요')
  deck=odds.deck(RNG,list(range(1,14))*32,w,lambda c:c-1)
  player=[deck.pop()];banker=[deck.pop()];player.append(deck.pop());banker.append(deck.pop())
  points=lambda hand:sum(c if c<10 else 0 for c in hand)%10
  p,b=points(player),points(banker)
  if max(p,b)<8:
   third=None
   if p<=5:third=deck.pop();player.append(third)
   t=0 if third is not None and third>=10 else third
   draw_banker=b<=5 if third is None else b<=2 or b==3 and t!=8 or b==4 and 2<=t<=7 or b==5 and 4<=t<=7 or b==6 and t in (6,7)
   if draw_banker:banker.append(deck.pop())
  p,b=points(player),points(banker);winner='tie' if p==b else 'player' if p>b else 'banker'
  payouts={k:config.get(k+'Multiplier',v) for k,v in [('player',2),('banker',1.95),('tie',9)]}
  mult=payouts[winner] if choice==winner else 1 if winner=='tie' and choice!='tie' else 0
  s.update(player=player,dealer=banker,playerPoints=p,bankerPoints=b,choice=choice,winner=winner)
  finish(s,mult,f'플레이어 {p}점 / 뱅커 {b}점 · '+dict(player='플레이어 승리',banker='뱅커 승리',tie='무승부')[winner])
 elif game=='slots':
  s['symbols']=[draw(5) for _ in range(3)]
  s['pairMultiplier']=config.get('pairMultiplier',0.5)
  s['tripleMultipliers']=list(config.get('tripleMultipliers',SLOT_TRIPLES))
  unique=len(set(s['symbols']))
  mult=s['tripleMultipliers'][s['symbols'][0]] if unique==1 else s['pairMultiplier'] if unique==2 else 0
  finish(s,mult,('세 개 일치!' if unique==1 else '두 개 일치!' if unique==2 else '모두 다른 모양')+f' · 원금 포함 {mult:g}배')
 elif game=='scratch':
  n=4;s['symbols']=[draw(n) for _ in range(3)]
  finish(s,n*n if len(set(s['symbols']))==1 else 0,'세 칸 일치!' if len(set(s['symbols']))==1 else '다음 기회에')
 elif game=='wheel':
  s['wheelMultipliers']=list(config.get('wheelMultipliers',[0,0,0,0,1,1,2,4]));s['segment']=draw(8);m=s['wheelMultipliers'][s['segment']];finish(s,m,f'{wheel_badge(m,s['segment'])} 칸에 멈췄어요')
 elif game=='roulette':
  if choice not in ('red','black','zero'):raise ValueError('red, black, zero 중 선택하세요')
  r=draw(37);s['roll']=r;color='zero' if r==0 else 'red' if r in RED else 'black'
  s['multipliers']={k:config.get(k+'Multiplier',36 if k=='zero' else 2) for k in ('red','black','zero')}
  mult=s['multipliers'][color] if choice==color else 0
  finish(s,mult,f"{r} · {dict(red='빨강',black='검정',zero='제로')[color]} · {multiplier_badge(mult)}")
 elif game=='horse':
  number(choice,1,5);s['order']=odds.sample(RNG,list(range(1,6)),5,w);finish(s,5 if s['order'][0]==choice else 0,f"{s['order'][0]}번 말 우승")
 elif game=='blackjack':
  deck=list(range(1,14))*24;deck=odds.deck(RNG,deck,w,lambda c:c-1);s.update(deck=deck,player=[deck.pop(),deck.pop()],dealer=[deck.pop(),deck.pop()])
  p,d=total(s['player']),total(s['dealer'])
  if p==21 or d==21:finish(s,1 if p==d else 2.5 if p==21 else 0,'자연 블랙잭 판정')
 elif game=='mines':s.update(hazards=odds.sample(RNG,list(range(9)),3,w),opened=[],mult=1)
 elif game=='bomb':s.update(hazards=[draw(5)],opened=[],mult=1)
 elif game=='tower':s.update(hazards=[draw(3) for _ in range(6)],opened=[],mult=1)
 elif game=='highlow':s.update(card=draw(13,1) if w else RNG.randint(1,13),mult=1)
 elif game=='baskin':s.update(count=0)
 elif game=='indian':s.update(player=draw(13,1) if w else RNG.randint(1,13),dealer=draw(13,1) if w else RNG.randint(1,13))
 elif game=='ttt':s.update(board=['']*9)
 return s

def action(s, act, value=None):
 if s['done']:raise ValueError('이미 종료된 게임입니다')
 g=s['game'];w=s.get('outcomeWeights',[])
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
  prev=s['card'];ways=(sum(w[prev:]) if act=='higher' else sum(w[:prev-1])) if w else (13-prev) if act=='higher' else (prev-1)
  if ways==0:raise ValueError('나올 수 없는 방향입니다')
  new=odds.choose(RNG,list(range(1,14)),w) if w else RNG.randint(1,13);s['card']=new;s['previous']=prev;s['step']+=1
  if not (new>prev if act=='higher' else new<prev):return finish(s,0,'예측 실패 (동점 포함)')
  s['mult']*=(sum(w) if w else 13)/ways
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
  limit=min(3,31-s['count']);bot=odds.choose(RNG,list(range(1,limit+1)),w[:limit]) if w else RNG.randint(1,limit);s['count']+=bot;s['botCount']=bot
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
  b[odds.choose(RNG,empty,[w[i] for i in empty]) if w else RNG.choice(empty)]='O'
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


odds_CARDS=['A','2','3','4','5','6','7','8','9','10','J','Q','K']
odds_CRASH_POINTS=[100,150,200,300,500,1000,2000,5000,10000]
def odds_spec(labels,note,positive=False,minimum=1):return dict(labels=labels,note=note,positive=positive,minimum=minimum)
odds_CATALOG={
 'baccarat':odds_spec(odds_CARDS,'8덱 · 양쪽 공통 카드 숫자 비중',True),
 'coin':odds_spec(list(map(str,range(1,7))),'주사위 숫자 비중 · 홀/짝 판정'),
 'dice':odds_spec(list(map(str,range(1,7))),'주사위 숫자 비중'),
 'slots':odds_spec(['🍒','🍋','🔔','⭐','💎'],'각 릴을 독립 추첨'),
 'scratch':odds_spec(['🍒','🍋','🔔','⭐'],'각 칸을 독립 추첨'),
 'wheel':odds_spec([str(i)+'번 칸' for i in range(1,9)],'돌림판 칸별 비중'),
 'roulette':odds_spec(list(map(str,range(37))),'룰렛 번호별 비중 · 색상은 번호로 결정'),
 'horse':odds_spec([str(i)+'번 말' for i in range(1,6)],'남은 말 중 순서대로 추첨',True),
 'mines':odds_spec([str(i)+'번 칸' for i in range(1,10)],'지뢰 위치 3개 · 중복 없이 순서대로 추첨 · 배당 공식 유지',minimum=3),
 'bomb':odds_spec([str(i)+'번 전선' for i in range(1,6)],'폭탄 전선 위치 · 배당 공식 유지'),
 'tower':odds_spec(['왼쪽','가운데','오른쪽'],'층마다 위험 발판 추첨 · 배당 공식 유지'),
 'highlow':odds_spec(odds_CARDS,'다음 카드 비중 · 배당은 실제 높음/낮음 확률에 반비례',minimum=2),
 'blackjack':odds_spec(odds_CARDS,'6덱에서 남은 카드 수 × 비중으로 추첨',True),
 'indian':odds_spec(odds_CARDS,'플레이어와 상대 모두 같은 카드 비중'),
 'baskin':odds_spec(['1개','2개','3개'],'봇이 셀 개수 · 가능한 선택 내 비율',True),
 'ttt':odds_spec([str(i)+'번 칸' for i in range(1,10)],'봇이 놓을 빈칸 비중',True),
 'holdem':odds_spec(['2','3','4','5','6','7','8','9','10','J','Q','K','A'],'52장 덱에서 남은 카드 수 × 숫자 비중 · 모든 참가자 공통',True),
 'lottery':odds_spec(list(map(str,range(1,21))),'당첨 번호 3개 · 중복 없이 추첨 (자동 구매 번호는 균등)',minimum=3),
 'crash':odds_spec([f'{x/100:g}배' for x in odds_CRASH_POINTS],'사용 시 나열된 배율 중 하나에서 종료 · 비우면 기존 연속 배율 공식'),
}
def odds_validate(values):
 if not isinstance(values,dict) or set(values)-set(odds_CATALOG):raise ValueError('게임 확률 설정을 확인하세요')
 for game,weights in values.items():
  rule=odds_CATALOG[game]
  if weights==[]:continue
  if not isinstance(weights,list) or len(weights)!=len(rule['labels']):raise ValueError(game+' 결과별 비중 개수를 확인하세요')
  if any(type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=1000000 for v in weights):raise ValueError('확률 비중은 0~1000000 사이 숫자입니다')
  if sum(v>0 for v in weights)<(len(weights) if rule['positive'] else rule['minimum']):raise ValueError(game+'의 양수 비중 개수가 부족합니다')
 return values

def odds_choose(rng,items,weights):
 if not weights:return rng.choice(items)
 return rng.choices(items,weights=weights,k=1)[0]

def odds_sample(rng,items,count,weights):
 if not weights:return rng.sample(list(items),count)
 pool=list(items);ws=list(weights);result=[]
 for _ in range(count):
  idx=odds_choose(rng,list(range(len(pool))),ws);result.append(pool.pop(idx));ws.pop(idx)
 return result

def odds_deck(rng,cards,weights,index):
 if not weights:
  rng.shuffle(cards);return cards
 # pop() draws the first selected card. Zero weights are forbidden for decks.
 return list(reversed(odds_sample(rng,cards,len(cards),[weights[index(c)] for c in cards])))

from types import SimpleNamespace
outcome_odds=SimpleNamespace(CATALOG=odds_CATALOG,CRASH_POINTS=odds_CRASH_POINTS,validate=odds_validate,choose=odds_choose,sample=odds_sample,deck=odds_deck)
odds=outcome_odds


def odds_preview(settings,game,choice=None,bet=100):
 """Pure preview: exact enumeration where possible; sampled strategy otherwise."""
 import itertools
 number(bet,1,100000000)
 if game not in CATALOG:raise ValueError('개인 게임을 선택하세요')
 cfg=settings['games'][game];weights=settings.get('probabilities',{}).get(game,[])
 cfg={**cfg,'outcomeWeights':weights};outcomes=[];method='정확 계산';strategy=''
 n={'coin':6,'dice':6,'slots':5,'scratch':4,'wheel':8,'roulette':37,'horse':5}.get(game)
 if game in ('dice','horse'):
  try:choice=int(choice)
  except (ValueError,TypeError):choice=1
 if game in ('coin','roulette','baccarat') and not choice:choice={'coin':'odd','roulette':'red','baccarat':'player'}[game]
 if n:
  w=weights or [1]*n;total_w=sum(w);p=[v/total_w for v in w]
  if game in ('slots','scratch'):
   for a,b,c in itertools.product(range(n),repeat=3):
    count=len({a,b,c});mult=(cfg.get('tripleMultipliers',SLOT_TRIPLES)[a] if count==1 else cfg.get('pairMultiplier',.5) if count==2 else 0) if game=='slots' else 16 if count==1 else 0
    outcomes.append((mult,p[a]*p[b]*p[c]))
  else:
   # Reuse validation for player choices.
   start(game,choice,cfg)
   for i,prob in enumerate(p):
    if game=='coin':mult=2 if ((i+1)%2==1)==(choice=='odd') else 0
    elif game=='dice':mult=6 if i+1==choice else 0
    elif game=='horse':mult=5 if i+1==choice else 0
    elif game=='wheel':mult=cfg.get('wheelMultipliers',[0,0,0,0,1,1,2,4])[i]
    else:
     color='zero' if i==0 else 'red' if i in RED else 'black';mult=cfg.get(color+'Multiplier',36 if color=='zero' else 2) if color==choice else 0
    outcomes.append((mult,prob))
 else:
  method='시뮬레이션 1,000판 · 추정치'
  strategy={'blackjack':'합계 17 이상이면 멈춤','indian':'항상 콜','baskin':'항상 1개 세기','ttt':'앞쪽 빈 칸부터 선택','highlow':'7 미만은 높음, 나머지는 낮음 · 1회 후 정산','mines':'1번 칸 1회 선택 후 정산','bomb':'1번 전선 1회 선택 후 정산','tower':'첫 층 1번 선택 후 정산','baccarat':'표준 바카라 규칙'}[game]
  for _ in range(1000):
   st=start(game,choice,cfg)
   for step in range(40):
    if st['done']:break
    if game=='blackjack':act,value=('hit' if total(st['player'])<17 else 'stand'),None
    elif game=='indian':act,value='call',None
    elif game=='baskin':act,value='count',1
    elif game=='ttt':act,value='pick',next(i for i,v in enumerate(st['board']) if not v)
    elif step:act,value='cashout',None
    elif game=='highlow':act,value=('higher' if st['card']<7 else 'lower'),None
    else:act,value='pick',0
    st=action(st,act,value)
   outcomes.append((st['mult'],.001))
 values=[(int(bet*m)-max(0,int(bet*m)-bet)*cfg['fee']//100,p) for m,p in outcomes]
 mean=sum(v*p for v,p in values);variance=sum(p*(v-mean)**2 for v,p in values)
 return dict(game=game,choice=choice,bet=bet,method=method,strategy=strategy,winChance=sum(p for v,p in values if v>bet)*100,returnRate=mean/bet*100,expectedProfit=mean-bet,margin95=1.96*math.sqrt(variance/1000)/bet*100 if not n else 0,fee=cfg['fee'])
