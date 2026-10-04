# Domain Context & Glossary: Indian Stock Market Trading Agent (MARkit)

## Core Entities & Concepts

### Trading Session & Market Clock
- **Market Open (`ACTIVE_MARKET`)**: 09:15 AM to 03:30 PM IST, Monday through Friday. Trading execution and order modification are strictly restricted to this window.
- **Auto Square-Off Window**: 03:15 PM to 03:30 PM IST. All open intraday positions are closed automatically to eliminate overnight gap risk.
- **Off-Hours (`OFF_HOURS_RESEARCH`)**: 03:30 PM to 09:00 AM IST and weekends. Trading is locked; the system exclusively runs financial news retrieval, sentiment analysis, technical screening, and macro analysis.
- **Pre-Market Briefing**: 09:00 AM to 09:15 AM IST. Synthesizes off-hours research into a prioritized daily watchlist and trading plan for market open.

### Ledger & Execution Simulation
- **Virtual Ledger**: In-memory and persisted double-entry paper ledger initialized with ₹10,000 INR cash.
- **Simulated Order**: Buy or sell order matched against real-world live tick/1-minute prices fetched from Indian exchanges (NSE/BSE).
- **Execution Friction**: Modeled real-world transaction costs including 0.05% price slippage, Securities Transaction Tax (STT), NSE turnover charges, GST, and SEBI regulatory fees.
- **Position**: An active intraday stock holding with tracked entry price, quantity, current market value, unrealized P&L, trailing stop-loss, and take-profit target.

### Risk Controls
- **Allocation Ceiling**: Maximum 30% of total capital per position (approx. ₹3,000 max commitment per stock).
- **Stop-Loss / Take-Profit**: Default 1.0%–1.5% stop-loss and 2.0%–3.0% take-profit target per trade.
- **Daily Circuit Breaker**: If total portfolio drawdown reaches 3% (₹300) in a single trading day, all active trading stops immediately until the next session.

### Agent Roles
- **Trader Agent**: Active-market loop responsible for analyzing live order-flow, technical signals, executing orders, and monitoring stops.
- **Research Agent**: Off-hours news scanner summarizing market catalysts, earnings updates, and macro headlines from Indian financial news feeds.
- **Trading Desk Dashboard**: Real-time web UI showing portfolio metrics, equity curve, live tickers, active positions, and streaming agent thought logs.
