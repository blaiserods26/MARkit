# Daily Trading Report & Performance Summary Generator

Status: resolved
Type: task
Blocked by: 02, 03, 05, 06

## Question

How should the post-market daily trade report and the cumulative common summary document (`Date -- Initial Amount -- Final Amount -- total number of trades -- Profit -- Loss`) be generated, structured, persisted, and integrated into the trading engine and web dashboard?

## Answer

Implemented the daily trading report generator and persistent summary tracking:
1. Core Reporter Module: [src/reporter.py](file:///c:/Users/Blaise%20Rodrigues/Desktop/MARkit/src/reporter.py)
   - Computes daily trade statistics in IST: Initial Amount, Final Amount, total trades, gross profit, gross loss, net P&L, Indian charges (STT, GST, etc.), slippage, and win rate.
   - Formats and writes comprehensive single-day markdown reports to `reports/trade_report_YYYY-MM-DD.md` and structured JSON to `reports/trade_report_YYYY-MM-DD.json`.
   - Maintains the common master document `reports/daily_summary.txt` with header `Date -- Initial Amount -- Final Amount -- total number of trades -- Profit -- Loss`, appending or updating exactly one line per day idempotently.
2. Agent Integration: [src/agent.py](file:///c:/Users/Blaise%20Rodrigues/Desktop/MARkit/src/agent.py)
   - Automatically runs report generation when trading day concludes (in `POST_MARKET_REVIEW` or off-hours after 15:30 IST).
   - Exposes manual `generate_daily_report()` hook on `TradingAgent`.
3. REST API Endpoints: [src/server.py](file:///c:/Users/Blaise%20Rodrigues/Desktop/MARkit/src/server.py)
   - `POST /api/reports/generate`: On-demand report generation.
   - `GET /api/reports/daily`: Today's or specific date's report metrics and trade breakdown.
   - `GET /api/reports/summary-document`: Raw text and parsed lines of `daily_summary.txt`.
   - `GET /api/reports/list`: List all generated reports.
4. Glassmorphic Web Dashboard: [static/index.html](file:///c:/Users/Blaise%20Rodrigues/Desktop/MARkit/static/index.html), [static/app.js](file:///c:/Users/Blaise%20Rodrigues/Desktop/MARkit/static/app.js), [static/style.css](file:///c:/Users/Blaise%20Rodrigues/Desktop/MARkit/static/style.css)
   - Added "Daily Report" header button and interactive modal with KPI metric cards, live master log viewer, and full trade parameters table.
5. Automated Tests: [tests/test_reporter.py](file:///c:/Users/Blaise%20Rodrigues/Desktop/MARkit/tests/test_reporter.py), [tests/test_server.py](file:///c:/Users/Blaise%20Rodrigues/Desktop/MARkit/tests/test_server.py), and [tests/test_agent.py](file:///c:/Users/Blaise%20Rodrigues/Desktop/MARkit/tests/test_agent.py) with all 45 test cases passing.

