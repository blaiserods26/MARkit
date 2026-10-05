# 03: Dynamic Nifty 50 Relative Volume (RVOL) & Momentum Screener

**What to build:** Dynamically screen the Nifty 50 universe to select the top 5 momentum and volume leaders for the session watchlist, replacing the static 6 mega-cap hardcoded list.

**Blocked by:** None (can start immediately)

**Status:** resolved

- [x] Add `screen_top_movers(limit=5)` to `MarketDataProvider` / `TradingAgent`.
- [x] Calculate percentage change and volume ratio relative to 20-day average.
- [x] Dynamically update `active_watchlist` in `TradingAgent` with the top volume/momentum leaders.
- [x] Fall back gracefully to primary liquid stocks if network screening is throttled.
- [x] Unit tests in `tests/test_market_data.py` and `tests/test_agent.py`.
