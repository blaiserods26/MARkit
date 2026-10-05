# 03: Dynamic Trailing Stop-Loss & Asymmetric Risk-Reward Gating

**What to build:** Improve profitability per trade by enforcing a mandatory minimum 1:2 Risk-to-Reward ratio (e.g. 1.0% stop-loss requires at least 2.0% target) before opening any position, and replace premature static profit-taking (RSI > 70) with a dynamic trailing stop-loss that locks in profits while allowing winning trends to run.

**Blocked by:** 01-trade-frequency-capping-and-cooldown-guardrails

**Status:** resolved

- [x] TradingAgent BUY setup evaluates target price and stop loss; if `(target - price) / (price - stop_loss) < 2.0`, the opportunity is rejected for insufficient risk/reward.
- [x] Position tracking in VirtualLedger/TradingAgent supports `highest_price` watermark and activates a trailing stop once unrealized profit exceeds +1.5% (trailing by 0.75% from peak).
- [x] Remove premature exit on `rsi > 70` when unrealized profit is positive unless trend breakdown occurs.
- [x] Unit tests in `tests/test_agent.py` and `tests/test_ledger.py` verifying trailing stop updates and R:R gating.
