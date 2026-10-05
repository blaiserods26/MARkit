# 04: Multi-Timeframe Trend & Volume Confirmation Engine

**What to build:** Elevate trade entry win rate by verifying both the 15-minute higher-timeframe trend and volume confirmation before taking a 5-minute setup, filtering out low-volume chops and false EMA crossovers.

**Blocked by:** 01-trade-frequency-capping-and-cooldown-guardrails

**Status:** resolved

- [x] Technical engine computes both 5m and 15m indicators (EMA fast, EMA slow, RSI) from market data history.
- [x] BUY setups require `trend_15m == "BULLISH"` as a gating filter for any 5m BUY signal.
- [x] Volume filter: require the most recent candle's volume to be at least 1.25x the 20-period moving average volume on that symbol.
- [x] Unit tests in `tests/test_agent.py` and `tests/test_market_data.py` testing MTF trend and volume checks.
