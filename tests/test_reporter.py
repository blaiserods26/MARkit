import os
import shutil
import tempfile
from datetime import datetime
import pytest

from src.clock import MarketClock, MarketState
from src.ledger import OrderSide, TradeRecord, VirtualLedger
from src.reporter import DailyReportGenerator, DailyReport


@pytest.fixture
def temp_reports_dir():
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def populated_ledger(tmp_path):
    ledger_path = str(tmp_path / "ledger.json")
    ledger = VirtualLedger(initial_cash=10000.0, persistence_path=ledger_path)
    ledger.day_start_equity = 10000.0

    # Add trades on 2026-10-05
    t1 = TradeRecord(
        trade_id="TRD-0001",
        symbol="INFY.NS",
        side=OrderSide.BUY,
        quantity=2,
        requested_price=1000.0,
        filled_price=1000.5,
        slippage=1.0,
        charges=0.15,
        net_amount=2001.15,
        pnl=0.0,
        reason="EMA crossover setup",
        timestamp="2026-10-05T09:30:00",
    )
    t2 = TradeRecord(
        trade_id="TRD-0002",
        symbol="INFY.NS",
        side=OrderSide.SELL,
        quantity=2,
        requested_price=1020.0,
        filled_price=1019.5,
        slippage=1.0,
        charges=0.65,
        net_amount=2038.35,
        pnl=37.20,
        reason="Target profit hit",
        timestamp="2026-10-05T10:15:00",
    )
    t3 = TradeRecord(
        trade_id="TRD-0003",
        symbol="TCS.NS",
        side=OrderSide.BUY,
        quantity=1,
        requested_price=3000.0,
        filled_price=3001.5,
        slippage=1.5,
        charges=0.25,
        net_amount=3001.75,
        pnl=0.0,
        reason="Breakout entry",
        timestamp="2026-10-05T11:00:00",
    )
    t4 = TradeRecord(
        trade_id="TRD-0004",
        symbol="TCS.NS",
        side=OrderSide.SELL,
        quantity=1,
        requested_price=2980.0,
        filled_price=2978.5,
        slippage=1.5,
        charges=0.95,
        net_amount=2977.55,
        pnl=-24.20,
        reason="Stop loss hit",
        timestamp="2026-10-05T11:45:00",
    )

    ledger.trades.extend([t1, t2, t3, t4])
    ledger.cash_balance = 10013.00
    ledger.realized_pnl = 13.00
    return ledger


def test_compute_daily_metrics(populated_ledger, temp_reports_dir):
    generator = DailyReportGenerator(ledger=populated_ledger, reports_dir=temp_reports_dir)
    report = generator.compute_daily_metrics("2026-10-05")

    assert report.date == "2026-10-05"
    assert report.total_trades == 4
    assert report.buy_trades == 2
    assert report.sell_trades == 2
    assert report.winning_trades == 1
    assert report.losing_trades == 1
    assert report.win_rate_pct == 50.0
    assert report.profit == 37.20
    assert report.loss == 24.20
    assert report.net_pnl == 13.00
    assert report.total_charges == round(0.15 + 0.65 + 0.25 + 0.95, 2)
    assert report.total_slippage == 5.0
    assert len(report.trades) == 4

    # Verify all trade parameters are present
    trade_item = report.trades[0]
    for key in [
        "trade_id", "timestamp", "symbol", "side", "quantity",
        "requested_price", "filled_price", "slippage", "charges",
        "net_amount", "pnl", "reason",
    ]:
        assert key in trade_item


def test_update_common_summary_document(populated_ledger, temp_reports_dir):
    generator = DailyReportGenerator(ledger=populated_ledger, reports_dir=temp_reports_dir)
    report = generator.compute_daily_metrics("2026-10-05")

    line = generator.update_common_summary_document(report)
    assert line == "2026-10-05 -- 10000.00 -- 10013.00 -- 4 -- 37.20 -- 24.20"

    content = generator.get_summary_document_content()
    lines = [l.strip() for l in content.splitlines() if l.strip()]
    assert len(lines) == 2
    assert lines[0] == "Date -- Initial Amount -- Final Amount -- total number of trades -- Profit -- Loss"
    assert lines[1] == "2026-10-05 -- 10000.00 -- 10013.00 -- 4 -- 37.20 -- 24.20"

    # Idempotency test: calling again for same date MUST NOT add duplicate lines
    generator.update_common_summary_document(report)
    content2 = generator.get_summary_document_content()
    lines2 = [l.strip() for l in content2.splitlines() if l.strip()]
    assert len(lines2) == 2, "Duplicate lines should not be added for the same day"

    # Adding a different day should append exactly one new line
    report_day2 = DailyReport(
        date="2026-10-06",
        initial_amount=10013.00,
        final_amount=10080.00,
        total_trades=2,
        buy_trades=1,
        sell_trades=1,
        winning_trades=1,
        losing_trades=0,
        win_rate_pct=100.0,
        profit=67.00,
        loss=0.00,
        net_pnl=67.00,
        total_charges=1.50,
        total_slippage=2.00,
        net_return_pct=0.67,
        trades=[],
        generated_at="2026-10-06T15:35:00",
    )
    generator.update_common_summary_document(report_day2)
    content3 = generator.get_summary_document_content()
    lines3 = [l.strip() for l in content3.splitlines() if l.strip()]
    assert len(lines3) == 3
    assert lines3[2] == "2026-10-06 -- 10013.00 -- 10080.00 -- 2 -- 67.00 -- 0.00"


def test_generate_and_save(populated_ledger, temp_reports_dir):
    generator = DailyReportGenerator(ledger=populated_ledger, reports_dir=temp_reports_dir)
    report, md_path, json_path = generator.generate_and_save("2026-10-05")

    assert os.path.exists(md_path)
    assert os.path.exists(json_path)

    with open(md_path, "r", encoding="utf-8") as f:
        md_text = f.read()
    assert "# 📊 MARkit Daily Trading Session Report" in md_text
    assert "TRD-0001" in md_text
    assert "INFY.NS" in md_text
    assert "2026-10-05 -- 10000.00 -- 10013.00 -- 4 -- 37.20 -- 24.20" in md_text

    reports_list = generator.list_reports()
    assert len(reports_list) == 1
    assert reports_list[0]["date"] == "2026-10-05"
    assert reports_list[0]["total_trades"] == 4


def test_zero_trades_day(tmp_path, temp_reports_dir):
    ledger_path = str(tmp_path / "ledger_empty.json")
    ledger = VirtualLedger(initial_cash=10000.0, persistence_path=ledger_path)
    generator = DailyReportGenerator(ledger=ledger, reports_dir=temp_reports_dir)

    report, md_path, json_path = generator.generate_and_save("2026-10-05")
    assert report.total_trades == 0
    assert report.profit == 0.0
    assert report.loss == 0.0
    assert report.net_pnl == 0.0
    assert report.win_rate_pct == 0.0

    content = generator.get_summary_document_content()
    lines = [l.strip() for l in content.splitlines() if l.strip()]
    assert lines[1] == "2026-10-05 -- 10000.00 -- 10000.00 -- 0 -- 0.00 -- 0.00"
