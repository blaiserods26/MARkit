# Real-Time NSE/BSE Market Data Feed Provider

Status: resolved
Type: research
Blocked by: none

## Question

What is the most reliable, zero-credential Python data feed approach for fetching real-time Indian stock market (NSE/BSE) live prices, 1-minute intraday bars, and quote snapshots with low latency and rate-limit resilience (e.g. `yfinance` `.NS`, `nselib`, unofficial NSE API endpoints, Google Finance)?

## Answer

`yfinance` with `.NS` suffixes provides reliable, zero-credential live prices via `ticker.fast_info` with historical 5m/1m fallback via `ticker.history()`. Implemented `MarketDataProvider` in [src/market_data.py](file:///c:/Users/blais/Desktop/AI%20Agents/MARkit/src/market_data.py) with in-memory TTL caching (10s), batch quote resolution, standardized IST timestamps, and liquid NIFTY 50 watchlist mapping. Validated with unit tests in [tests/test_market_data.py](file:///c:/Users/blais/Desktop/AI%20Agents/MARkit/tests/test_market_data.py). OpenBLAS environment limits (`OPENBLAS_NUM_THREADS=1`) configured to guarantee stability.

