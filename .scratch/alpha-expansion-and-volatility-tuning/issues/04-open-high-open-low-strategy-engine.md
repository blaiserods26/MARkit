# 04: Open=High / Open=Low (OHL) Institutional Strategy Engine

**What to build:** Detect the classical Indian market institutional order-flow setup where a stock's opening price equals its daily low in the first 15 minutes (Open = Low), providing high-conviction breakout setups.

**Blocked by:** 03-dynamic-nifty50-rvol-screener

**Status:** resolved

- [x] Add `detect_ohl_pattern(symbol)` in technical analysis checking if `abs(Open - Low) / Open < 0.001` (Open=Low) or `abs(Open - High) / Open < 0.001` (Open=High).
- [x] For Open=Low stocks, boost BUY setup confidence by +0.15 and set stop-loss at the day's open.
- [x] For Open=High stocks, filter out BUY setups (bearish institutional control).
- [x] Unit tests in `tests/test_agent.py`.
