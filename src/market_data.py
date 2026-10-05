"""
Market Data Provider for Indian Stock Exchanges (NSE / BSE).
Uses zero-credential yfinance with caching, fallback mechanisms, and standardized IST timestamps.
"""

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
from typing import Dict, List, Optional
import pandas as pd
import requests
import yfinance as yf

logger = logging.getLogger(__name__)

# Liquid NIFTY 50 top universe for algorithmic paper trading
NIFTY_50_TICKERS: List[str] = [
    "RELIANCE.NS",
    "TCS.NS",
    "HDFCBANK.NS",
    "INFY.NS",
    "ICICIBANK.NS",
    "BHARTIARTL.NS",
    "SBIN.NS",
    "LICI.NS",
    "ITC.NS",
    "HINDUNILVR.NS",
    "LT.NS",
    "BAJFINANCE.NS",
    "MARUTI.NS",
    "M&M.NS",
    "KOTAKBANK.NS",
    "AXISBANK.NS",
    "TITAN.NS",
    "ASIANPAINT.NS",
    "SUNPHARMA.NS",
    "TATASTEEL.NS",
]


@dataclass
class QuoteSnapshot:
    symbol: str
    price: float
    day_high: float
    day_low: float
    change_pct: float
    volume: int
    timestamp: datetime
    currency: str = "INR"


class MarketDataProvider:
    def __init__(self, cache_ttl_seconds: int = 10, history_cache_ttl_seconds: int = 60):
        self._cache_ttl = timedelta(seconds=cache_ttl_seconds)
        self._history_ttl = timedelta(seconds=history_cache_ttl_seconds)
        self._quote_cache: Dict[str, tuple[datetime, QuoteSnapshot]] = {}
        self._history_cache: Dict[str, tuple[datetime, pd.DataFrame]] = {}
        self._last_known_quotes: Dict[str, QuoteSnapshot] = {}
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
        })

    def get_nifty50_symbols(self) -> List[str]:
        """Return the curated list of highly liquid NIFTY 50 tickers."""
        return list(NIFTY_50_TICKERS)

    def get_live_quote(self, symbol: str) -> Optional[QuoteSnapshot]:
        """
        Fetch real-time or latest available quote for an Indian stock symbol.
        Leverages yfinance fast_info and historical fallback with short-term caching.
        """
        now = datetime.now()
        # Return cached quote if still valid
        if symbol in self._quote_cache:
            cache_time, cached_quote = self._quote_cache[symbol]
            if now - cache_time < self._cache_ttl:
                return cached_quote

        ticker = yf.Ticker(symbol, session=self._session)
        price = None
        day_high = None
        day_low = None
        prev_close = None
        volume = 0

        # Tier 1: Try yfinance fast_info safely (guard against KeyError / scraper crashes)
        try:
            fast = ticker.fast_info
            p = getattr(fast, "last_price", None)
            if p is not None and not pd.isna(p) and float(p) > 0:
                price = float(p)
                day_high = getattr(fast, "day_high", None)
                day_low = getattr(fast, "day_low", None)
                prev_close = getattr(fast, "previous_close", None)
                volume = getattr(fast, "last_volume", 0) or 0
        except Exception as fe:
            logger.debug(f"fast_info lookup failed for {symbol}: {fe}")

        # Tier 2: Fallback to recent intraday history and metadata if fast_info missing or failed
        if price is None or price <= 0 or math.isnan(price):
            try:
                hist = ticker.history(period="1d", interval="1m")
                if hist.empty:
                    hist = ticker.history(period="5d", interval="5m")
                if not hist.empty:
                    md = {}
                    try:
                        md = ticker.get_history_metadata() or {}
                    except Exception:
                        pass
                    last_row = hist.iloc[-1]
                    price = float(md.get("regularMarketPrice") or last_row["Close"])
                    day_high = float(md.get("regularMarketDayHigh") or (hist["High"].max() if "High" in hist else price))
                    day_low = float(md.get("regularMarketDayLow") or (hist["Low"].min() if "Low" in hist else price))
                    prev_close = float(md.get("chartPreviousClose") or (hist["Close"].iloc[-2] if len(hist) > 1 else price))
                    volume = int(md.get("regularMarketVolume") or last_row.get("Volume", 0))
            except Exception as he:
                logger.warning(f"History quote fallback failed for {symbol}: {he}")

        # Tier 3: Return last known quote if available before giving up
        if price is None or price <= 0 or math.isnan(price):
            if symbol in self._last_known_quotes:
                logger.warning(f"Using last known quote for {symbol} due to upstream data provider failure")
                return self._last_known_quotes[symbol]
            logger.error(f"Could not fetch valid price for {symbol}")
            return None

        try:
            price = round(float(price), 2)
            day_high = round(float(day_high if day_high and not pd.isna(day_high) else price), 2)
            day_low = round(float(day_low if day_low and not pd.isna(day_low) else price), 2)

            change_pct = 0.0
            if prev_close and not pd.isna(prev_close) and float(prev_close) > 0:
                change_pct = round(((price - float(prev_close)) / float(prev_close)) * 100, 2)

            snapshot = QuoteSnapshot(
                symbol=symbol,
                price=price,
                day_high=day_high,
                day_low=day_low,
                change_pct=change_pct,
                volume=int(volume or 0),
                timestamp=now,
                currency="INR",
            )

            self._quote_cache[symbol] = (now, snapshot)
            self._last_known_quotes[symbol] = snapshot
            return snapshot

        except Exception as e:
            logger.warning(f"Error computing quote snapshot for {symbol}: {e}")
            if symbol in self._last_known_quotes:
                return self._last_known_quotes[symbol]
            return None

    def get_batch_quotes(self, symbols: List[str]) -> Dict[str, QuoteSnapshot]:
        """
        Fetch quotes for multiple tickers in batch.
        """
        quotes: Dict[str, QuoteSnapshot] = {}
        for sym in symbols:
            quote = self.get_live_quote(sym)
            if quote:
                quotes[sym] = quote
        return quotes

    def screen_top_movers(self, limit: int = 5) -> List[str]:
        """
        Dynamically screen liquid Nifty 50 constituents for highest absolute change/volume momentum.
        Falls back to primary liquid tickers if screening fails.
        """
        candidates = self.get_nifty50_symbols()[:12]
        quotes = self.get_batch_quotes(candidates)
        if not quotes:
            return candidates[:limit]

        sorted_symbols = sorted(
            quotes.keys(),
            key=lambda s: abs(quotes[s].change_pct),
            reverse=True,
        )
        return sorted_symbols[:limit] if sorted_symbols else candidates[:limit]

    def get_intraday_history(
        self, symbol: str, interval: str = "5m", period: str = "5d"
    ) -> pd.DataFrame:
        """
        Retrieve intraday OHLCV bars for technical indicator computation.
        Uses in-memory 60s TTL cache to avoid hitting external rate limits.
        """
        cache_key = f"{symbol}_{interval}_{period}"
        now = datetime.now()
        if cache_key in self._history_cache:
            cache_time, cached_df = self._history_cache[cache_key]
            if now - cache_time < self._history_ttl:
                return cached_df.copy()

        try:
            ticker = yf.Ticker(symbol, session=self._session)
            df = ticker.history(period=period, interval=interval)
            if df.empty:
                # Fallback to longer period if weekend / holiday
                df = ticker.history(period="1mo", interval="15m")
            if not df.empty:
                self._history_cache[cache_key] = (now, df)
            return df
        except Exception as e:
            logger.exception(f"Error fetching intraday history for {symbol}: {e}")
            return pd.DataFrame()
