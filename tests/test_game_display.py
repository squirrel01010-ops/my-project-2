import unittest,json
import social_bot,bot
class GameDisplay(unittest.TestCase):
 def test_crash_hides_internal_values_and_shows_actual_end(self):
  s=dict(kind='crash',id='INTERNAL_ID',status='done',starts=0,multiplier=2.99,crash=1.59,players=[],commitment='SECRET_HASH',seed='SECRET_SEED')
  text=json.dumps(social_bot.embed(s).to_dict(),ensure_ascii=False)
  for token in ('INTERNAL_ID','SECRET_HASH','SECRET_SEED','seed','2.99'):self.assertNotIn(token,text)
  self.assertIn('1.59',text)
 def test_solo_symbols_and_cards_are_readable(self):
  r=dict(game='slots',bet=10,status='done',payout=0,state=dict(symbols=[0,1,2]))
  self.assertIn('🍒　│　🍋　│　🔔',bot.game_embed(r).description)
  r.update(game='blackjack',state=dict(player=[1,13],dealer=[10,None]),status='active')
  e=bot.game_embed(r)
  self.assertIn('│ A  │',e.description);self.assertIn('│ K  │',e.description);self.assertIn('│ ▧  │',e.description)

 def test_loss_omits_fee_and_keeps_signed_amount(self):
  r=dict(game='slots',bet=100,status='done',payout=50,fee=15,state=dict(symbols=[0,0,1],mult=0.5))
  e=bot.game_embed(r)
  self.assertEqual(e.fields[0].name,'📉 손실')
  self.assertIn('-50',e.fields[0].value)
  self.assertNotIn('수수료',json.dumps(e.to_dict(),ensure_ascii=False))
  r['payout']=200
  e=bot.game_embed(r)
  self.assertIn('수수료 15%',e.fields[0].name)
  self.assertIn('+100',e.fields[0].value)
  self.assertNotIn('수수료',social_bot.profit_text(-50,15))
