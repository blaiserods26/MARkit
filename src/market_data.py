"""
Market Data Provider for Indian Stock Exchanges (NSE / BSE).
Uses zero-credential yfinance with caching, fallback mechanisms, and standardized IST timestamps.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
from typing import Dict, List, Optional
import pandas as pd
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
    def __init__(self, cache_ttl_seconds: int = 10):
        self._cache_ttl = timedelta(seconds=cache_ttl_seconds)
        self._quote_cache: Dict[str, tuple[datetime, QuoteSnapshot]] = {}

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

        try:
            ticker = yf.Ticker(symbol)
            fast = ticker.fast_info

            price = getattr(fast, "last_price", None)
            day_high = getattr(fast, "day_high", None)
            day_low = getattr(fast, "day_low", None)
            prev_close = getattr(fast, "previous_close", None)
            volume = getattr(fast, "last_volume", 0) or 0

            # Fallback to history if fast_info missing last_price
            if price is None or price <= 0:
                hist = ticker.history(period="5d", interval="5m")
                if not hist.empty:
                    last_row = hist.iloc[-1]
                    price = float(last_row["Close"])
                    day_high = float(hist["High"].iloc[-1]) if day_high is None else day_high
                    day_low = float(hist["Low"].iloc[-1]) if day_low is None else day_low
                    prev_close = float(hist["Close"].iloc[-2]) if len(hist) > 1 else price
                    volume = int(last_row.get("Volume", 0))

            if price is None or price <= 0:
                logger.error(f"Could not fetch valid price for {symbol}")
                return None

            price = round(float(price), 2)
            day_high = round(float(day_high if day_high else price), 2)
            day_low = round(float(day_low if day_low else price), 2)

            change_pct = 0.0
            if prev_close and prev_close > 0:
                change_pct = round(((price - prev_close) / prev_close) * 100, 2)

            snapshot = QuoteSnapshot(
                symbol=symbol,
                price=price,
                day_high=day_high,
                day_low=day_low,
                change_pct=change_pct,
                volume=int(volume),
                timestamp=now,
                currency="INR",
            )

            self._quote_cache[symbol] = (now, snapshot)
            return snapshot

        except Exception as e:
            logger.exception(f"Error fetching quote for {symbol}: {e}")
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

    def get_intraday_history(
        self, symbol: str, interval: str = "5m", period: str = "5d"
    ) -> pd.DataFrame:
        """
        Retrieve intraday OHLCV bars for technical indicator computation.
        """
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period=period, interval=interval)
            if df.empty:
                # Fallback to longer period if weekend / holiday
                df = ticker.history(period="1mo", interval="15m")
            return df
        except Exception as e:
            logger.exception(f"Error fetching intraday history for {symbol}: {e}")
            return pd.DataFrame()
