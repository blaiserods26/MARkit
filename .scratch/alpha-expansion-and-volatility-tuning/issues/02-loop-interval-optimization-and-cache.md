# 02: Loop Interval Optimization & Rate-Limit Shield

**What to build:** Adjust background autonomous trading cycle interval from 15 seconds to 60 seconds and add lightweight in-memory quote and candle caching in `MarketDataProvider`, preventing Yahoo Finance rate limits and throttling.

**Blocked by:** None (can start immediately)

**Status:** resolved

- [x] Set `cycle_interval_seconds = 60` in `src/server.py`.
- [x] Add TTL-based in-memory caching (e.g. 45-60s) for historical intraday candle data in `MarketDataProvider`.
- [x] Ensure live quotes for open position monitoring bypass cache or use low-TTL (5-10s) to maintain responsive trailing stop tracking.
- [x] Unit tests in `tests/test_server.py` and `tests/test_market_data.py`.
