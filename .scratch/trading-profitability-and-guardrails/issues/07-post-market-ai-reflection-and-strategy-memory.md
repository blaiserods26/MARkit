# 07: Post-Market AI Reflection & Strategy Memory Loop

**What to build:** Feed the closed trading session's reports, slippage, and P&L back into Gemini at market close (15:30 IST) to synthesize an automated "Lessons Learned" review, highlighting what worked and what didn't, and adjusting dynamic parameters for the next day.

**Blocked by:** 01-trade-frequency-capping-and-cooldown-guardrails, 03-dynamic-trailing-stop-loss-and-risk-reward-gating

**Status:** resolved

- [x] In `DailyReportGenerator` / `TradingAgent`, add post-market Gemini reflection prompt analyzing gross profit vs loss, slippage friction, and win rate.
- [x] Save the generated reflection into `reports/trade_report_<date>.md` and a dedicated `reports/ai_lessons.json` history.
- [x] Surface AI reflection summaries on the trading desk dashboard.
- [x] Unit tests in `tests/test_reporter.py` and `tests/test_agent.py`.
