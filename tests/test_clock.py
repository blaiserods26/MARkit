from datetime import datetime
import pytz
import pytest
from src.clock import MarketClock, MarketState

IST = pytz.timezone("Asia/Kolkata")

def test_active_market_hours():
    clock = MarketClock()
    # Wednesday 10:30 AM IST
    mock_dt = datetime(2026, 10, 7, 10, 30, 0, tzinfo=IST)
    state = clock.get_market_state(mock_dt)
    assert state == MarketState.ACTIVE_MARKET
    can_trade, reason = clock.is_trading_allowed(mock_dt)
    assert can_trade is True

def test_auto_squareoff_hours():
    clock = MarketClock()
    # Wednesday 15:20 IST (3:20 PM)
    mock_dt = datetime(2026, 10, 7, 15, 20, 0, tzinfo=IST)
    state = clock.get_market_state(mock_dt)
    assert state == MarketState.AUTO_SQUAREOFF
    can_trade, reason = clock.is_trading_allowed(mock_dt)
    assert can_trade is False
    assert clock.is_squareoff_window(mock_dt) is True

def test_weekend_off_hours():
    clock = MarketClock()
    # Sunday 12:00 PM IST
    mock_dt = datetime(2026, 10, 4, 12, 0, 0, tzinfo=IST)
    state = clock.get_market_state(mock_dt)
    assert state == MarketState.OFF_HOURS_RESEARCH
    can_trade, reason = clock.is_trading_allowed(mock_dt)
    assert can_trade is False
    assert "weekend" in reason.lower()

def test_pre_market_hours():
    clock = MarketClock()
    # Monday 09:05 AM IST
    mock_dt = datetime(2026, 10, 5, 9, 5, 0, tzinfo=IST)
    state = clock.get_market_state(mock_dt)
    assert state == MarketState.PRE_MARKET_BRIEFING
    can_trade, _ = clock.is_trading_allowed(mock_dt)
    assert can_trade is False

def test_night_research_hours():
    clock = MarketClock()
    # Thursday 21:00 (9:00 PM IST)
    mock_dt = datetime(2026, 10, 8, 21, 0, 0, tzinfo=IST)
    state = clock.get_market_state(mock_dt)
    assert state == MarketState.OFF_HOURS_RESEARCH
    can_trade, _ = clock.is_trading_allowed(mock_dt)
    assert can_trade is False

def test_entry_cutoff_hours():
    clock = MarketClock()
    # Wednesday 14:10 IST - before cutoff, entry allowed
    mock_dt_before = datetime(2026, 10, 7, 14, 10, 0, tzinfo=IST)
    allowed, reason = clock.is_entry_allowed(mock_dt_before)
    assert allowed is True

    # Wednesday 14:20 IST - after cutoff, entry blocked
    mock_dt_after = datetime(2026, 10, 7, 14, 20, 0, tzinfo=IST)
    allowed, reason = clock.is_entry_allowed(mock_dt_after)
    assert allowed is False
    assert "cutoff" in reason.lower()
