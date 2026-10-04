import pytest
from src.agent import TradingAgent, AgentDecision, ActionType
from src.ledger import VirtualLedger
from src.market_data import MarketDataProvider
from src.clock import MarketClock, MarketState
from src.research import NewsResearcher

@pytest.fixture
def agent():
    ledger = VirtualLedger(initial_cash=10000.0, persistence_path="tests/test_agent_ledger.json")
    provider = MarketDataProvider()
    clock = MarketClock()
    researcher = NewsResearcher()
    ag = TradingAgent(
        ledger=ledger,
        market_data=provider,
        clock=clock,
        researcher=researcher
    )
    yield ag
    import os
    if os.path.exists("tests/test_agent_ledger.json"):
        os.remove("tests/test_agent_ledger.json")

def test_compute_technical_signals(agent):
    signals = agent.compute_technicals("RELIANCE.NS")
    assert "rsi" in signals
    assert "ema_fast" in signals
    assert "ema_slow" in signals
    assert "trend" in signals
    assert 0 <= signals["rsi"] <= 100

def test_evaluate_opportunity_structure(agent):
    decision = agent.evaluate_opportunity("RELIANCE.NS")
    assert isinstance(decision, AgentDecision)
    assert decision.symbol == "RELIANCE.NS"
    assert decision.action in (ActionType.BUY, ActionType.SELL, ActionType.HOLD)
    assert decision.reasoning
    assert 0 <= decision.confidence <= 1.0

def test_market_hours_lock_on_buy(agent):
    import pytz
    from datetime import datetime
    IST = pytz.timezone("Asia/Kolkata")
    # Sunday midnight (off-hours)
    sunday_dt = datetime(2026, 10, 4, 1, 0, 0, tzinfo=IST)
    res = agent.execute_trade_cycle(mock_dt=sunday_dt)
    assert res["status"] == "OFF_HOURS"
    assert "trades_executed" in res
    assert len(res["trades_executed"]) == 0
    assert "research_brief" in res

def test_thought_log_recording(agent):
    agent.log_thought(
        thought="Evaluating NIFTY 50 top liquid constituents for intraday setup.",
        action="SCAN_WATCHLIST",
        details={"symbols_scanned": 5}
    )
    logs = agent.get_thought_logs(limit=5)
    assert len(logs) >= 1
    assert logs[-1]["action"] == "SCAN_WATCHLIST"
