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
  self.assertEqual(bot.game_embed(r).fields[0].value,'🍒 │ 🍋 │ 🔔')
  r.update(game='blackjack',state=dict(player=[1,13],dealer=[10,None]),status='active')
  e=bot.game_embed(r)
  self.assertEqual(e.fields[0].value,'A K');self.assertEqual(e.fields[1].value,'10 🂠')
