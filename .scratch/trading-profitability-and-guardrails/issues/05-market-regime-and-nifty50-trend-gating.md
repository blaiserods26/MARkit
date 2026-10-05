# 05: Benchmark NIFTY 50 Market Regime Gating

**What to build:** Protect the portfolio against entering long positions when the overall Indian market is weak, by gating all BUY orders against the live direction and VWAP of `^NSEI` (NIFTY 50).

**Blocked by:** 04-multi-timeframe-trend-and-volume-confirmation

**Status:** resolved

- [x] Add market regime evaluator in `TradingAgent` / `MarketDataProvider` for `^NSEI`.
- [x] If NIFTY 50 trend is `BEARISH` (or price < VWAP / EMA21 on intraday charts), block all new BUY orders and log `MARKET_REGIME_BEARISH_HALT`.
- [x] Allow an override only for stocks displaying exceptional relative strength and strong bullish news sentiment.
- [x] Unit tests in `tests/test_agent.py` asserting BUY blocking when Nifty 50 is bearish.
