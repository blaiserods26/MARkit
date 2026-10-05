# Spec: Trading Profitability & Execution Guardrails

## Background
On the first live trading session (2026-10-05), the agent suffered a net loss of ₹61.99 (-0.62%) on an initial capital of ₹10,000. Analysis revealed that over 85% of this loss (₹52.89) was caused by excessive execution friction (STT, GST, SEBI fees, exchange fees, and 0.05% slippage) across 32 executions (16 round trips). The core failure modes were:
1. Rapid whipsaw churn (re-entering symbols within seconds of exiting at a loss).
2. Premature profit taking (selling winners at +₹1 on RSI > 70 while letting full stop-losses hit).
3. Initiating trades late in the session (e.g. at 15:00 IST) right before 15:15 auto square-off.
4. No higher-timeframe trend or market regime alignment.

## Core Architectural Objectives
1. **Friction Defense**: Cap maximum daily trades, enforce symbol-level exit cooldowns (20 mins), and require minimum position dwell times.
2. **Session Timing**: Enforce an entry cutoff window at 14:15 IST (no new positions opened after 14:15).
3. **Asymmetric Risk/Reward & Trailing Stops**: Require minimum 1:2 R:R at entry and trail stop-losses on winning positions instead of chopping them on RSI > 70.
4. **Signal Filtration**: Require 15-minute trend alignment and volume surge (> 1.5x 20-MA volume) on 5-minute triggers.
5. **Market Regime Gating**: Block individual long entries if the benchmark NIFTY 50 index is below VWAP or trending bearishly.
6. **Pre-Market & Post-Market AI Loops**: Elevate Gemini's role from single-tick validator to macro sector ranker in pre-market (09:00-09:15) and analytical reflection reviewer at market close (15:30).
