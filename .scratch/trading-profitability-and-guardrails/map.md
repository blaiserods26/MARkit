# Map: Trading Profitability & Execution Guardrails

## Notes
- First session on 2026-10-05 lost ₹61.99 due to 32 trades with ₹52.89 in friction (slippage + regulatory fees).
- Implemented execution guardrails, timing cutoffs, dynamic trailing stops, multi-timeframe volume confirmation, NIFTY 50 regime gating, and post-market AI reflection loops.

## Frontier
- [x] 01: Trade Frequency Capping & Cooldown Guardrails
- [x] 02: Session Timing Gates & Entry Cutoff Window
- [x] 03: Dynamic Trailing Stop-Loss & Asymmetric Risk-Reward Gating
- [x] 04: Multi-Timeframe Trend & Volume Confirmation Engine
- [x] 05: Benchmark NIFTY 50 Market Regime Gating
- [x] 06: Pre-Market Strategic Sector Ranking & Catalyst Briefing
- [x] 07: Post-Market AI Reflection & Strategy Memory Loop

## Decisions-so-far
- Capped daily round-trip trades to 5 to protect from statutory fee bleed.
- Implemented 20-minute symbol cooldown after any exit to prevent instant re-buying whipsaws.
- Enforced 10-minute minimum position dwell time before indicator-based exits (hard stop-losses remain immediate).
- Added `ENTRY_CUTOFF_TIME = time(14, 15)` to `MarketClock` and `TradingAgent` to prevent entries without runway before 15:15 auto square-off.
- Added dynamic trailing stop to `Position` (activates at +1.5% profit, trails peak by 0.75%), eliminating premature RSI > 70 exits.
- Enforced $\ge 1:2$ Risk-to-Reward ratio for all BUY trade setups.
- Integrated 15m trend confirmation (`trend_15m`) and 20-period volume moving average confirmation (`vol_ratio`).
- Added NIFTY 50 benchmark market regime check (`^NSEI`) to prevent long entries when the broader market is in a downtrend.
- Implemented `generate_ai_reflection` in `TradingAgent` saving post-market insights to `reports/ai_lessons.json`.
- All 51 unit and integration tests passing.
