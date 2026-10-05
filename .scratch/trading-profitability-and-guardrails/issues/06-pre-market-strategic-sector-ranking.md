# 06: Pre-Market Strategic Sector Ranking & Catalyst Briefing

**What to build:** Shift Gemini's role from a low-level tick validator to a macro catalyst and sector ranker during the 09:00–09:15 pre-market briefing, generating a ranked watchlist with key support and resistance levels for the trading session.

**Blocked by:** 02-session-timing-gates-and-entry-cutoff

**Status:** resolved

- [x] Enhance `pre_market_plan` generation in `TradingAgent` to prompt Gemini for sector strength rankings and key catalyst watchlists between 09:00 and 09:15 IST.
- [x] Incorporate daily pivot/support/resistance levels into the pre-market plan data structure.
- [x] Filter intraday symbol scanning to focus preferentially on the top-ranked pre-market symbols.
- [x] Unit tests in `tests/test_agent.py` and `tests/test_research.py`.
