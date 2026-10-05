# 01: ATR-Based Dynamic Volatility Stop-Loss & Target Sizing

**What to build:** Compute 14-period Average True Range (ATR) per stock and dynamically set stop-loss ($1.5 \times \text{ATR}$) and profit target ($3.0 \times \text{ATR}$), replacing static 1.0% and 2.5% percentages so setups adapt realistically to stock volatility.

**Blocked by:** None (can start immediately)

**Status:** resolved

- [x] Technicals engine in `TradingAgent` computes 14-period ATR from intraday price history.
- [x] BUY candidate setup sets `stop_loss = round(price - 1.5 * atr, 2)` and `target_price = round(price + 3.0 * atr, 2)`.
- [x] Preserves minimum 1:2 Risk-to-Reward ratio by construction (3.0 ATR reward / 1.5 ATR risk = 2.0).
- [x] Unit tests in `tests/test_agent.py` asserting ATR computation and dynamic stop/target values.
