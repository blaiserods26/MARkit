# Paper Trading Ledger & Order Execution Simulator

Status: resolved
Type: prototype
Blocked by: none

## Question

How should the in-memory and persisted paper trading ledger be designed to accurately track cash balance (starting at ₹10,000 INR), open intraday positions, executed trades, P&L, realistic 0.05% slippage, and Indian regulatory charges (STT, exchange turnover fees, GST, SEBI turnover fees, stamp duty)?

## Answer

Implemented `VirtualLedger` and statutory Indian charges calculation in [src/ledger.py](file:///c:/Users/blais/Desktop/AI%20Agents/MARkit/src/ledger.py). Accurately models:
1. Indian statutory charges: STT (0.025% on sell), NSE turnover fees (0.00297%), SEBI turnover fees (0.0001%), Stamp duty (0.003% on buy), and 18% GST.
2. Execution friction: 0.05% slippage adverse impact on fills.
3. Position risk rules: 30% capital allocation ceiling per trade (max ₹3,000 on ₹10,000 capital).
4. Circuit breaker: 3% (₹300) daily drawdown threshold halting further trading for the session.
5. Persistent JSON storage for orders, active positions, and trade history.
Validated through 6 automated test cases in [tests/test_ledger.py](file:///c:/Users/blais/Desktop/AI%20Agents/MARkit/tests/test_ledger.py).

