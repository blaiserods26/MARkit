# 02: Session Timing Gates & Entry Cutoff Window

**What to build:** Enforce an intraday entry cutoff time at 14:15 IST. After 14:15 IST, the agent is strictly prohibited from opening any new positions, ensuring trades are never initiated without sufficient runway before the 15:15 IST mandatory square-off window.

**Blocked by:** None (can start immediately)

**Status:** resolved

- [x] Add `is_entry_allowed(dt)` / `ENTRY_CUTOFF_TIME = time(14, 15)` to `MarketClock` and `TradingAgent`.
- [x] During active market hours, if current time is >= 14:15 IST, BUY order scans are bypassed and logged with a clear rationale.
- [x] Open positions entered before 14:15 continue to be monitored normally for stop-loss and targets until 15:15 auto square-off.
- [x] Unit tests in `tests/test_clock.py` and `tests/test_agent.py` validating that entries are blocked at 14:15+ while exits remain functional.
