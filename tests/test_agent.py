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

def test_unheld_stock_cannot_be_sold(agent):
    # Ensure RELIANCE is not held
    assert "RELIANCE.NS" not in agent.ledger.positions
    decision = agent.evaluate_opportunity("RELIANCE.NS", is_held=False)
    # Unheld stock must NEVER return SELL (stocks must be purchased before selling)
    assert decision.action != ActionType.SELL
    assert decision.action in (ActionType.BUY, ActionType.HOLD)

def test_held_stock_can_be_sold(agent):
    from src.ledger import OrderSide
    # Purchase stock first so it is held
    agent.ledger.execute_order(
        symbol="INFY.NS",
        side=OrderSide.BUY,
        quantity=2,
        current_price=1000.0,
    )
    assert "INFY.NS" in agent.ledger.positions
    pos = agent.ledger.positions["INFY.NS"]

    # Now evaluate opportunity with is_held=True
    decision = agent.evaluate_opportunity("INFY.NS", is_held=True, held_position=pos)
    # Held stock can produce SELL or HOLD, but NEVER BUY
    assert decision.action in (ActionType.SELL, ActionType.HOLD)
    assert decision.action != ActionType.BUY

def test_purchase_order_budget_limits(agent):
    max_val = agent.ledger.get_max_purchase_value()
    # 30% of ₹10,000 = ₹3,000
    assert max_val <= 3000.0
    # Buy quantity of stock at ₹1,500 must not exceed 2 shares
    max_qty = agent.ledger.get_max_buy_quantity(1500.0)
    assert max_qty == 2

def test_cash_debit_and_credit_cycle(agent):
    from src.ledger import OrderSide
    initial_cash = agent.ledger.cash_balance
    assert initial_cash == 10000.0

    # Execute BUY: cash must be debited
    buy_res = agent.ledger.execute_order(
        symbol="TCS.NS",
        side=OrderSide.BUY,
        quantity=1,
        current_price=2000.0,
    )
    assert buy_res.trade is not None
    assert agent.ledger.cash_balance < initial_cash
    assert agent.ledger.cash_balance == round(initial_cash - buy_res.trade.net_amount, 2)

    # Execute SELL: cash must be credited
    sell_res = agent.ledger.execute_order(
        symbol="TCS.NS",
        side=OrderSide.SELL,
        quantity=1,
        current_price=2100.0,
    )
    assert sell_res.trade is not None
    assert agent.ledger.cash_balance > initial_cash - buy_res.trade.net_amount
    assert "TCS.NS" not in agent.ledger.positions

