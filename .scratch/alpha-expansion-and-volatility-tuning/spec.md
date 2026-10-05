# Spec: Alpha Expansion & Volatility Tuning

## Background
With execution friction and over-trading successfully contained by guardrails, the next operational milestone is improving alpha generation, risk-adjusted returns, and system stability:
1. **Static targets vs Reality**: Low-beta stocks cannot reach fixed 2.5% intraday targets, while high-beta stocks get prematurely stopped out by a 1.0% stop. ATR (Average True Range) dynamically sizes stops and targets to stock-specific volatility.
2. **Polling Overhead**: A 15-second loop querying 7 symbols causes 15-20 external requests every 15s. Moving to 60s with candle caching shields against Yahoo Finance rate-limits.
3. **Static Watchlist Trap**: Trading the same 6 mega-caps every day misses the strongest trending stocks of the session. An intraday RVOL screener dynamically identifies the top 5 momentum movers across NIFTY 50.
4. **Institutional Open Flow**: In the Indian market, Open=Low indicates institutional buying from the 09:15 open, providing high-conviction breakout setups.
5. **Bear Market Profitability**: When NIFTY 50 is bearish, sitting 100% in cash misses opportunities. Supporting Intraday Shorting (MIS) allows the bot to profit on market down days.
