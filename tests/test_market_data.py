import pytest
from datetime import datetime
from src.market_data import MarketDataProvider, QuoteSnapshot

def test_nifty50_symbols_list():
    provider = MarketDataProvider()
    symbols = provider.get_nifty50_symbols()
    assert len(symbols) >= 10
    assert "RELIANCE.NS" in symbols
    assert "TCS.NS" in symbols
    assert "HDFCBANK.NS" in symbols

def test_quote_snapshot_dataclass():
    snap = QuoteSnapshot(
        symbol="RELIANCE.NS",
        price=1167.70,
        day_high=1175.0,
        day_low=1160.0,
        change_pct=-0.25,
        volume=1250000,
        timestamp=datetime.now(),
        currency="INR"
    )
    assert snap.symbol == "RELIANCE.NS"
    assert snap.price == 1167.70
    assert snap.currency == "INR"

def test_fetch_live_quote():
    provider = MarketDataProvider()
    quote = provider.get_live_quote("RELIANCE.NS")
    assert quote is not None
    assert quote.symbol == "RELIANCE.NS"
    assert quote.price > 0
    assert quote.currency == "INR"

def test_fetch_batch_quotes():
    provider = MarketDataProvider()
    tickers = ["RELIANCE.NS", "TCS.NS", "INFY.NS"]
    quotes = provider.get_batch_quotes(tickers)
    assert len(quotes) == 3
    for ticker in tickers:
        assert ticker in quotes
        assert quotes[ticker].price > 0

def test_fetch_intraday_history():
    provider = MarketDataProvider()
    df = provider.get_intraday_history("RELIANCE.NS", interval="5m", period="5d")
    assert not df.empty
    assert "Close" in df.columns
    assert "Volume" in df.columns
