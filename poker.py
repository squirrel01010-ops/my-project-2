"""One-hand 2–6 player no-limit hold'em with exact integer side-pot settlement."""
from collections import Counter
from itertools import combinations
import secrets
RNG=secrets.SystemRandom()
LABELS=['하이 카드','원페어','투페어','트리플','스트레이트','플러시','풀하우스','포카드','스트레이트 플러시']

def rank5(cards):
 ranks=[c%13+2 for c in cards];counts=Counter(ranks);groups=sorted(((n,r) for r,n in counts.items()),reverse=True)
 unique=sorted(set(ranks),reverse=True);straight=5 if unique==[14,5,4,3,2] else unique[0] if len(unique)==5 and unique[0]-unique[4]==4 else 0
 flush=len({c//13 for c in cards})==1
 if flush and straight:return (8,straight)
 if groups[0][0]==4:return (7,groups[0][1],groups[1][1])
 if [g[0] for g in groups]==[3,2]:return (6,groups[0][1],groups[1][1])
 if flush:return (5,*sorted(ranks,reverse=True))
 if straight:return (4,straight)
 if groups[0][0]==3:return (3,groups[0][1],*sorted([r for r in ranks if r!=groups[0][1]],reverse=True))
 pairs=sorted([r for r,n in counts.items() if n==2],reverse=True)
 if len(pairs)==2:return (2,*pairs,next(r for r,n in counts.items() if n==1))
 if pairs:return (1,pairs[0],*sorted([r for r in ranks if r!=pairs[0]],reverse=True))
 return (0,*sorted(ranks,reverse=True))
def rank(cards):return max(rank5(c) for c in combinations(cards,5))
def card(c):return ['♠','♥','♦','♣'][c//13]+{11:'J',12:'Q',13:'K',14:'A'}.get(c%13+2,str(c%13+2))
def take(p,amount):
 amount=min(amount,p['stack']);p['stack']-=amount;p['round']+=amount;p['total']+=amount;return amount

def begin(s,now):
 deck=list(range(52));RNG.shuffle(deck);s.update(deck=deck,board=[],street='preflop',bet=s['blind'],min_raise=s['blind'],status='active',dealer=RNG.randrange(len(s['players'])),payouts={},history=[])
 for p in s['players']:p.update(cards=[deck.pop(),deck.pop()],round=0,total=0,folded=False,acted=None)
 n=len(s['players']);d=s['dealer'];sb=d if n==2 else (d+1)%n;bb=(sb+1)%n
 take(s['players'][sb],max(1,s['blind']//2));take(s['players'][bb],s['blind']);s['turn']=(bb+1)%n
 advance(s,(s['turn']-1)%n,now)
 return s

def showdown(s):
 alive=[p for p in s['players'] if not p['folded']];awards={p['uid']:0 for p in s['players']};pots=[]
 if len(alive)==1:awards[alive[0]['uid']]=sum(p['total'] for p in s['players'])
 else:
  ranks={p['uid']:rank(p['cards']+s['board']) for p in alive};previous=0
  for height in sorted({p['total'] for p in s['players'] if p['total']>0}):
   contributors=[p for p in s['players'] if p['total']>=height];amount=(height-previous)*len(contributors);previous=height
   eligible=[p for p in contributors if not p['folded']]
   if not eligible:raise ValueError('홀덤 팟 분배 상태 오류')
   best=max(ranks[p['uid']] for p in eligible);winners=[p['uid'] for p in eligible if ranks[p['uid']]==best]
   # Odd chips go clockwise from the seat left of the dealer.
   order=[s['players'][(s['dealer']+i)%len(s['players'])]['uid'] for i in range(1,len(s['players'])+1)]
   winners.sort(key=order.index);part,odd=divmod(amount,len(winners))
   for i,uid in enumerate(winners):awards[uid]+=part+(i<odd)
   pots.append(dict(amount=amount,winners=winners))
  s['hands']={uid:LABELS[r[0]] for uid,r in ranks.items()}
 s['pots']=pots;s['payouts']={p['uid']:p['stack']+awards[p['uid']] for p in s['players']};s['status']='done';s['turn']=None;s['message']='쇼다운' if len(alive)>1 else '모두 폴드하여 승리'
 return s

def advance(s,after,now):
 while True:
  alive=[p for p in s['players'] if not p['folded']]
  if len(alive)==1:return showdown(s)
  able=[p for p in alive if p['stack']>0]
  pending=[p for p in able if p['acted'] is None or p['round']<s['bet']]
  if len(able)==1 and able[0]['round']>=s['bet']:pending=[]
  if pending:
   for offset in range(1,len(s['players'])+1):
    i=(after+offset)%len(s['players'])
    if s['players'][i] in pending:s['turn']=i;s['deadline']=now+s['turn_seconds'];return s
  if s['street']=='river':return showdown(s)
  nextstreet={'preflop':('flop',3),'flop':('turn',1),'turn':('river',1)}[s['street']];s['street']=nextstreet[0]
  s['deck'].pop() # Burn a card.
  s['board'] += [s['deck'].pop() for _ in range(nextstreet[1])]
  s['bet']=0;s['min_raise']=s['blind']
  for p in s['players']:p['round']=0;p['acted']=None
  after=s['dealer']

def act(s,uid,action,value,now):
 if s['status']!='active':raise ValueError('진행 중인 테이블이 아닙니다')
 p=s['players'][s['turn']]
 if p['uid']!=uid:raise PermissionError('본인 차례에만 행동할 수 있습니다')
 if now>=s['deadline']:raise ValueError('행동 시간이 지났습니다. 테이블을 새로고침하세요')
 i=s['turn'];owed=max(0,s['bet']-p['round'])
 if action=='fold':p['folded']=True
 elif action=='check':
  if owed:raise ValueError('콜할 금액이 있어 체크할 수 없습니다')
 elif action=='call':take(p,owed)
 elif action in ('raise','allin'):
  target=p['round']+p['stack'] if action=='allin' else value
  if type(target) is not int or target<=p['round'] or target>p['round']+p['stack']:raise ValueError('레이즈는 이번 라운드 총 베팅액으로 입력하세요')
  if target<=s['bet']:
   if action!='allin':raise ValueError('현재 베팅보다 큰 금액을 입력하세요')
   take(p,target-p['round'])
  else:
   if p['acted'] is not None and s['bet']-p['acted']<s['min_raise']:raise ValueError('짧은 올인으로는 레이즈 권한이 다시 열리지 않습니다')
   increase=target-s['bet']
   if increase<s['min_raise'] and target!=p['round']+p['stack']:raise ValueError(f"최소 레이즈 총액은 {s['bet']+s['min_raise']}입니다")
   take(p,target-p['round']);s['bet']=target
   if increase>=s['min_raise']:s['min_raise']=increase
 else:raise ValueError('잘못된 홀덤 동작')
 p['acted']=s['bet'];s['history']=(s['history']+[dict(uid=uid,action=action,round=p['round'])])[-20:]
 return advance(s,i,now)

def view(s,viewer=None):
 # Explicit allowlist: never expose deck, burn cards or other players' hole cards.
 out={k:s[k] for k in ('id','host','channel','buyin','blind','status','created','lobby_end','revision','turn_seconds') if k in s}
 for k in ('board','street','bet','min_raise','dealer','turn','deadline','message','payouts','pots','hands','history'):
  if k in s:out[k]=s[k]
 out['board']=[card(c) for c in s.get('board',[])]
 out['players']=[]
 for p in s['players']:
  item={k:p[k] for k in ('uid','name','stack','round','total','folded','acted') if k in p}
  reveal=p['uid']==viewer or (s['status']=='done' and len([x for x in s['players'] if not x.get('folded')])>1 and not p.get('folded'))
  item['cards']=[card(c) for c in p.get('cards',[])] if reveal else ['🂠','🂠'] if 'cards' in p else []
  out['players'].append(item)
 return out
