# STELLAR interface

The Discord bot and admin site share a navy, mint, and muted rose palette. The Discord game logic remains in `games.py`, `core.py`, and `social.py`; presentation does not change balances, probabilities, or settlement.

- `public/style.css`: responsive layout, game cards, forms, tables, dialogs, fixed settings save bar, reduced-motion support.
- `public/app.js`: individual game setting cards, settings shortcuts and unsaved-change guard, game boards and result presentation.
- `public/social.js`: compact multiplayer entry cards, live crash multiplier.
- `bot.py` / `game_motion.py`: rank-only card boards, contextual instructions, clear payout and balance fields; cashout disabled until a valid first action. Roulette and wheel animation sequences are preserved.
- `social_bot.py`: compact hold'em table, lottery net prize pool, automatically refreshed crash results. Never display internal IDs, commitments, seeds, or another player's hidden cards.

Use `/관리` to open a fresh private login link. Asset URLs carry a presentation version so a reopened dashboard gets the current styles. Existing Discord messages update when a game is next displayed or edited; live social games use a bumped display fingerprint.

## Validation

Run the Python unittest suite with discord.py and python-dotenv installed. The browser checks use Playwright with `/usr/bin/chromium` and isolated temporary databases, never the deployed database.

```
.venv/bin/python -m unittest discover -s tests -p 'test_*.py' -q
node tests/settings-save.cjs
node tests/design-preview.cjs
```

The design preview checks eight pages at widths 320, 390 and 1440, social tabs, visible save controls, and a playable bomb board. Screenshots are written under `/tmp/stellar-*.png` using sample accounts only.
