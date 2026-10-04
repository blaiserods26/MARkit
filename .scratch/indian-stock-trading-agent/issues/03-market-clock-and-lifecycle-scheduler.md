# Indian Market Clock & Lifecycle State Machine

Status: resolved
Type: prototype
Blocked by: none

## Question

How should the Indian market clock and state machine (`ACTIVE_MARKET` 09:15–15:30 IST Mon–Fri, `AUTO_SQUAREOFF` 15:15–15:30 IST, `OFF_HOURS_RESEARCH` 15:30–09:00 IST & weekends, `PRE_MARKET` 09:00–09:15 IST) be structured to strictly enforce trading locks outside market hours while orchestrating off-hours research routines?

## Answer

Implemented `MarketClock` and `MarketState` in [src/clock.py](file:///c:/Users/blais/Desktop/AI%20Agents/MARkit/src/clock.py) utilizing the `Asia/Kolkata` timezone. Correctly models:
1. `ACTIVE_MARKET` (09:15–15:15 IST): BUY and SELL allowed.
2. `AUTO_SQUAREOFF` (15:15–15:30 IST): New buy orders rejected, position square-offs triggered.
3. `POST_MARKET_REVIEW` (15:30–16:00 IST): Trading locked, day P&L finalized.
4. `OFF_HOURS_RESEARCH` (16:00–09:00 IST and all weekends): Trading execution blocked, agent restricted to research.
5. `PRE_MARKET_BRIEFING` (09:00–09:15 IST): Watchlist and day plan compilation.
Validated via test suite in [tests/test_clock.py](file:///c:/Users/blais/Desktop/AI%20Agents/MARkit/tests/test_clock.py).

