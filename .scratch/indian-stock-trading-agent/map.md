# Wayfinder Map: Indian Stock Market Trading Agent (MARkit)

Label: wayfinder:map

## Destination

An autonomous Python trading & research agent with a paper-trading simulation ledger (₹10,000 starting capital), real-time Indian stock market feeds (NSE/BSE), strict market-hours enforcement (09:15–15:30 IST active trading, off-hours research), risk circuit breakers, and a sleek real-time dark-mode web dashboard.

## Notes

- Domain glossary: [CONTEXT.md](file:///c:/Users/blais/Desktop/AI%20Agents/MARkit/CONTEXT.md)
- Core tech stack: Python 3.10+, FastAPI, Google GenAI SDK (Gemini tool-calling), Vanilla HTML5/CSS3/ES6 JS with SSE/WebSockets for dashboard.
- Market rules: Indian Standard Time (IST, UTC+5:30). 09:15–15:30 IST active market trading; 15:15 IST intraday square-off; off-hours research only.
- Strict simulation: Realistic Indian market friction (0.05% slippage, STT, turnover fees, GST, SEBI fees).
- Capital: ₹10,000 INR; max 30% per trade; 3% daily drawdown circuit breaker.

## Decisions so far
- [Real-Time NSE/BSE Market Data Feed Provider](issues/01-nse-realtime-data-feed.md): Integrated zero-credential yfinance provider with TTL caching, fast_info live quotes, historical fallback, and liquid NIFTY 50 universe.
- [Paper Trading Ledger & Order Execution Simulator](issues/02-paper-trading-ledger-and-order-simulator.md): Built VirtualLedger with ₹10,000 INR balance, Indian STT/GST/SEBI statutory fees, 0.05% slippage, 30% allocation cap, 3% circuit breaker, and JSON persistence.
- [Indian Market Clock & Lifecycle State Machine](issues/03-market-clock-and-lifecycle-scheduler.md): Implemented MarketClock with Asia/Kolkata timezone enforcing active market (09:15-15:15), auto square-off (15:15-15:30), post-market review, and off-hours research locks.
- [Financial News Research & Sentiment Analysis Tool](issues/04-financial-news-research-and-sentiment-tool.md): Built NewsResearcher combining Google News RSS and Economic Times feeds with financial lexicon sentiment scoring and pre-market briefings.
- [Trading Agent Decision Engine & Execution Loop](issues/05-trading-agent-decision-engine.md): Implemented TradingAgent orchestrating technical indicators (RSI, EMA), news sentiment, position monitoring, and market lifecycle transitions.
- [Real-Time Dark-Mode Trading Desk Dashboard](issues/06-fastapi-realtime-trading-dashboard.md): Built modern glassmorphic trading desk dashboard (FastAPI + Vanilla CSS/JS) with live IST clock, thought stream, metrics, watchlist, and order simulation.

## Not yet specified

- Multi-broker production adapter layer (Zerodha Kite Connect / Angel One SmartAPI live trading toggle)
- Dynamic universe screening beyond NIFTY 50 (e.g. Midcap momentum breakouts, volume shockers)
- Long-term historical strategy backtesting engine and walk-forward parameter optimization

## Out of scope

- Real money order placement / live broker trade execution (strictly simulated paper trading)
- F&O (Futures & Options) and derivatives trading (equity cash segment intraday only)
- High-frequency tick-level algorithmic market making
