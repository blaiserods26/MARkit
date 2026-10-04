# Trading Agent Decision Engine & Execution Loop

Status: resolved
Type: prototype
Blocked by: 01, 02, 03, 04

## Question

How should the lightweight autonomous agent loop be structured using direct Gemini API tool-calling to evaluate technical indicators, cross-reference news sentiment, size orders under the 30% capital rule, enforce the 3% daily circuit breaker, and execute buy/sell/square-off actions?

## Answer

Implemented `TradingAgent` in [src/agent.py](file:///c:/Users/blais/Desktop/AI%20Agents/MARkit/src/agent.py). Features:
1. Technical indicator engine: RSI-14, EMA 9 / 21 crossovers, and trend determination from live intraday bars.
2. Signal synthesis: Combines technical momentum with news sentiment score from `NewsResearcher`.
3. Sizing & Risk: Caps positions at 30% total equity, sets 1.5% stop-losses and 3.0% take-profit targets, and halts trading if the 3% daily circuit breaker triggers.
4. Market Clock lifecycle execution: Automatically invokes square-off during the 15:15–15:30 IST window, runs pre-market briefings and macro news research off-hours, and monitors active positions during live hours.
5. Structured thought logs: Real-time logging of thoughts, actions, and decisions for user and UI observability.
Validated with unit test suite in [tests/test_agent.py](file:///c:/Users/blais/Desktop/AI%20Agents/MARkit/tests/test_agent.py).

