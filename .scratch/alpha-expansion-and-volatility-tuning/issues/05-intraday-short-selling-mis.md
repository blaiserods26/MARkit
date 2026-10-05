# 05: Intraday Short-Selling (MIS) During Bearish Market Regimes

**What to build:** Support Indian Intraday Shorting (MIS): opening short positions on high-volume breakdown stocks when the benchmark NIFTY 50 regime is bearish, allowing the agent to profit during market downturns instead of sitting idle in 100% cash.

**Blocked by:** 01-atr-based-dynamic-volatility-stop-loss

**Status:** resolved

- [x] Extend `Position` in `VirtualLedger` to support `side: OrderSide = OrderSide.BUY` (LONG or SHORT).
- [x] For SHORT positions, unrealized PnL is `quantity * (average_entry_price - current_price)`.
- [x] During `MARKET_REGIME_BEARISH`, allow `SELL` to open an intraday short position on a breakdown stock with stop loss above resistance.
- [x] Ensure 15:15 auto square-off closes both Long and Short positions completely.
- [x] Unit tests in `tests/test_ledger.py` and `tests/test_agent.py` verifying short trade execution, P&L calculations, and square-off.
