import os
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


def test_agent_eod_report_generation(agent, tmp_path):
    import pytz
    from datetime import datetime
    IST = pytz.timezone("Asia/Kolkata")

    # Set temporary reports dir
    reports_dir = str(tmp_path / "reports")
    agent.reporter.reports_dir = reports_dir
    agent.reporter.summary_doc_path = os.path.join(reports_dir, "daily_summary.txt")
    os.makedirs(reports_dir, exist_ok=True)

    # Monday at 15:35 IST (POST_MARKET_REVIEW)
    post_market_dt = datetime(2026, 10, 5, 15, 35, 0, tzinfo=IST)
    res = agent.execute_trade_cycle(mock_dt=post_market_dt)

    assert "daily_report" in res
    assert res["daily_report"] is not None
    assert res["daily_report"]["date"] == "2026-10-05"
    assert os.path.exists(agent.reporter.summary_doc_path)

    # Direct on-demand call
    manual_rep = agent.generate_daily_report("2026-10-05")
    assert manual_rep.date == "2026-10-05"
    assert agent.last_report_date == "2026-10-05"


def test_symbol_cooldown_blocks_rebuy(agent):
    import pytz
    from datetime import datetime, timedelta
    from src.ledger import OrderSide
    IST = pytz.timezone("Asia/Kolkata")
    now_dt = datetime(2026, 10, 7, 10, 30, 0, tzinfo=IST)

    # Simulate exiting INFY at 10:30
    agent.symbol_cooldowns["INFY.NS"] = now_dt

    # Cycle 5 minutes later (10:35) -> still within 20m cooldown
    check_dt = now_dt + timedelta(minutes=5)
    res = agent.execute_trade_cycle(mock_dt=check_dt)
    
    # Verify INFY was not bought
    infy_trades = [t for t in res["trades_executed"] if t.get("symbol") == "INFY.NS"]
    assert len(infy_trades) == 0


def test_dwell_time_protects_open_position(agent):
    import pytz
    from datetime import datetime, timedelta
    from src.ledger import OrderSide, Position
    IST = pytz.timezone("Asia/Kolkata")
    open_time = datetime(2026, 10, 7, 10, 0, 0, tzinfo=IST)

    quote = agent.market_data.get_live_quote("RELIANCE.NS")
    curr_price = quote.price if quote else 1000.0

    pos = Position(
        symbol="RELIANCE.NS",
        quantity=2,
        average_entry_price=curr_price,
        current_price=curr_price,
        stop_loss=round(curr_price * 0.985, 2),
        target=round(curr_price * 1.05, 2),
        opened_at=open_time.isoformat(),
    )
    agent.ledger.positions["RELIANCE.NS"] = pos

    # 3 minutes later (within 10-minute dwell window)
    eval_dt = open_time + timedelta(minutes=3)
    dec = agent.evaluate_opportunity("RELIANCE.NS", is_held=True, held_position=pos, current_dt=eval_dt)
    
    # Must HOLD to protect against indicator jitter
    assert dec.action == ActionType.HOLD
    assert "dwell window" in dec.reasoning.lower()


def test_dynamic_trailing_stop_activation(agent):
    from src.ledger import OrderSide, Position
    pos = Position(
        symbol="TCS.NS",
        quantity=1,
        average_entry_price=1000.0,
        current_price=1000.0,
        stop_loss=990.0,
        target=1050.0,
        highest_price=1000.0,
    )
    agent.ledger.positions["TCS.NS"] = pos

    # Price moves up by 2.0% to 1020 (>= 1.5% activation)
    pos.update_price(1020.0)
    new_sl = pos.check_trailing_stop(activation_gain_pct=0.015, trail_distance_pct=0.0075)

    assert new_sl is not None
    assert new_sl > 990.0
    # Peak 1020 - 0.75% = 1012.35
    assert new_sl == round(1020.0 * (1 - 0.0075), 2)
    assert pos.stop_loss == new_sl


def test_entry_cutoff_blocks_new_buys_in_cycle(agent):
    import pytz
    from datetime import datetime
    IST = pytz.timezone("Asia/Kolkata")

    # 14:25 IST - active market but after 14:15 cutoff
    cutoff_dt = datetime(2026, 10, 7, 14, 25, 0, tzinfo=IST)
    res = agent.execute_trade_cycle(mock_dt=cutoff_dt)
    
    # Trades executed must be 0
    assert len(res["trades_executed"]) == 0
    # Last thought log should mention cutoff
    logs = agent.get_thought_logs(limit=5)
    cutoff_logged = any("cutoff" in l["thought"].lower() for l in logs)
    assert cutoff_logged is True


def test_max_daily_trade_cap(agent):
    import pytz
    from datetime import datetime
    from src.ledger import OrderSide, TradeRecord
    IST = pytz.timezone("Asia/Kolkata")
    now_dt = datetime(2026, 10, 7, 11, 0, 0, tzinfo=IST)
    today_str = now_dt.strftime("%Y-%m-%d")

    # Fake 5 BUY trades today
    for i in range(5):
        agent.ledger.trades.append(
            TradeRecord(
                trade_id=f"TRD-{i+1:04d}",
                symbol="MOCK.NS",
                side=OrderSide.BUY,
                quantity=1,
                requested_price=100.0,
                filled_price=100.0,
                slippage=0.05,
                charges=0.1,
                net_amount=100.15,
                timestamp=f"{today_str}T10:{i:02d}:00",
            )
        )

    # Next cycle should halt new entries
    res = agent.execute_trade_cycle(mock_dt=now_dt)
    assert len(res["trades_executed"]) == 0
    logs = agent.get_thought_logs(limit=5)
    limit_logged = any("limit reached" in l["thought"].lower() for l in logs)
    assert limit_logged is True


