import os
import pytest
from src.ledger import VirtualLedger, OrderSide, OrderStatus

TEST_LEDGER_PATH = "tests/test_ledger.json"

@pytest.fixture
def ledger():
    if os.path.exists(TEST_LEDGER_PATH):
        os.remove(TEST_LEDGER_PATH)
    led = VirtualLedger(initial_cash=10000.0, persistence_path=TEST_LEDGER_PATH)
    yield led
    if os.path.exists(TEST_LEDGER_PATH):
        os.remove(TEST_LEDGER_PATH)

def test_initial_ledger_state(ledger):
    assert ledger.cash_balance == 10000.0
    assert ledger.initial_cash == 10000.0
    assert len(ledger.positions) == 0
    assert len(ledger.trades) == 0
    assert ledger.daily_drawdown_pct == 0.0

def test_buy_order_execution_and_charges(ledger):
    # Buy 2 shares of RELIANCE at 1000 INR
    res = ledger.execute_order(
        symbol="RELIANCE.NS",
        side=OrderSide.BUY,
        quantity=2,
        current_price=1000.0,
        stop_loss=985.0,
        target=1030.0,
        reason="Momentum breakout"
    )
    assert res.status == OrderStatus.FILLED
    assert res.filled_price > 1000.0  # Includes slippage (0.05%)
    assert res.charges > 0  # Stamp duty + GST + exchange fee
    assert "RELIANCE.NS" in ledger.positions
    pos = ledger.positions["RELIANCE.NS"]
    assert pos.quantity == 2
    assert ledger.cash_balance < 10000.0 - 2000.0

def test_sell_to_square_off_position(ledger):
    # Buy 2 shares at 1000
    ledger.execute_order(
        symbol="RELIANCE.NS",
        side=OrderSide.BUY,
        quantity=2,
        current_price=1000.0,
    )
    # Sell at 1050 (profit)
    res = ledger.execute_order(
        symbol="RELIANCE.NS",
        side=OrderSide.SELL,
        quantity=2,
        current_price=1050.0,
        reason="Target achieved"
    )
    assert res.status == OrderStatus.FILLED
    assert "RELIANCE.NS" not in ledger.positions
    assert ledger.realized_pnl > 0
    assert ledger.cash_balance > 10000.0  # Net profit after charges

def test_allocation_ceiling_rejection(ledger):
    # ₹10,000 initial cash, max 30% = ₹3,000 per position
    # Trying to buy ₹5,000 worth should be rejected
    res = ledger.execute_order(
        symbol="TCS.NS",
        side=OrderSide.BUY,
        quantity=2,
        current_price=2500.0,  # 2 * 2500 = 5000 > 3000 limit
    )
    assert res.status == OrderStatus.REJECTED
    assert "allocation limit" in res.message.lower()
    assert "TCS.NS" not in ledger.positions

def test_daily_circuit_breaker(ledger):
    # Simulate a loss that triggers 3% drawdown (>= 300 INR loss)
    # Buy 2 shares at 1000
    ledger.execute_order(
        symbol="INFY.NS",
        side=OrderSide.BUY,
        quantity=2,
        current_price=1000.0,
    )
    # Sell at 800 (400 INR loss > 300 INR circuit breaker)
    ledger.execute_order(
        symbol="INFY.NS",
        side=OrderSide.SELL,
        quantity=2,
        current_price=800.0,
    )
    assert ledger.circuit_breaker_triggered is True

    # Subsequent orders must be rejected
    res = ledger.execute_order(
        symbol="SBIN.NS",
        side=OrderSide.BUY,
        quantity=1,
        current_price=500.0,
    )
    assert res.status == OrderStatus.REJECTED
    assert "circuit breaker" in res.message.lower()

def test_persistence(ledger):
    ledger.execute_order(
        symbol="RELIANCE.NS",
        side=OrderSide.BUY,
        quantity=1,
        current_price=1000.0,
    )
    # Reload ledger from file
    loaded = VirtualLedger(initial_cash=10000.0, persistence_path=TEST_LEDGER_PATH)
    assert loaded.cash_balance == ledger.cash_balance
    assert "RELIANCE.NS" in loaded.positions
    assert loaded.positions["RELIANCE.NS"].quantity == 1
