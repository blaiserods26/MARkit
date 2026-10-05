# 01: Trade Frequency Capping & Cooldown Guardrails

**What to build:** Protect the account from friction bleed by limiting total executions to a maximum of 5 round-trip trades per day, enforcing a 20-minute cooldown on any symbol after it is exited before it can be re-bought, and requiring a minimum 10-minute position dwell time before non-stop-loss technical exits can occur.

**Blocked by:** None (can start immediately)

**Status:** resolved

- [x] Daily trade count limit (default 5 round-trip trades/day) enforced in TradingAgent before initiating new BUY orders.
- [x] Symbol exit cooldown timestamp dictionary tracked in TradingAgent; new BUY orders for a recently exited symbol are rejected if within the cooldown window (default 20 minutes).
- [x] Minimum dwell time (default 10 minutes from `opened_at`) enforced before indicator-based exits (e.g. minor EMA dip) are permitted, while hard stop-loss exits remain immediate.
- [x] Unit tests in `tests/test_agent.py` covering trade cap, symbol cooldown, and dwell time.
