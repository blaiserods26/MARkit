# Financial News Research & Sentiment Analysis Tool

Status: resolved
Type: prototype
Blocked by: none

## Question

How should the research tool aggregate and parse live Indian financial news (Moneycontrol, Economic Times, LiveMint, NSE corporate announcements) and score sentiment for NIFTY 50 stocks during off-hours and pre-market sessions without requiring paid third-party search APIs?

## Answer

Implemented `NewsResearcher` in [src/research.py](file:///c:/Users/blais/Desktop/AI%20Agents/MARkit/src/research.py). Features:
1. Multi-source RSS aggregation: Google News RSS for stock-specific feeds and Economic Times RSS for Indian market macro headlines.
2. Domain-tailored financial sentiment scoring: Evaluates corporate earnings, management commentary, deal wins, regulatory actions, and returns normalized sentiment scores (-1.0 to +1.0) and classifications (`BULLISH`, `BEARISH`, `NEUTRAL`).
3. Automated pre-market briefings and headline caching.
4. Zero paid external API keys required.
Validated via test suite in [tests/test_research.py](file:///c:/Users/blais/Desktop/AI%20Agents/MARkit/tests/test_research.py).

