"""
Daily Trading Report & Performance Summary Generator.
Generates post-market single-day trade reports with full execution parameters,
and maintains a common document with one line appended per day:
Date -- Initial Amount -- Final Amount -- total number of trades -- Profit -- Loss
"""

from dataclasses import dataclass, asdict
from datetime import datetime
import json
import logging
import os
from typing import Dict, List, Optional, Tuple
import pytz

from src.clock import MarketClock, IST
from src.ledger import OrderSide, TradeRecord, VirtualLedger

logger = logging.getLogger(__name__)


@dataclass
class DailyReport:
    date: str
    initial_amount: float
    final_amount: float
    total_trades: int
    buy_trades: int
    sell_trades: int
    winning_trades: int
    losing_trades: int
    win_rate_pct: float
    profit: float
    loss: float
    net_pnl: float
    total_charges: float
    total_slippage: float
    net_return_pct: float
    trades: List[Dict]
    generated_at: str


class DailyReportGenerator:
    """
    Produces daily trade reports and maintains cumulative daily performance tracking.
    """

    SUMMARY_HEADER = "Date -- Initial Amount -- Final Amount -- total number of trades -- Profit -- Loss"

    def __init__(
        self,
        ledger: VirtualLedger,
        clock: Optional[MarketClock] = None,
        reports_dir: str = "reports",
        summary_doc_path: Optional[str] = None,
    ):
        self.ledger = ledger
        self.clock = clock or MarketClock()
        self.reports_dir = reports_dir
        self.summary_doc_path = summary_doc_path or os.path.join(reports_dir, "daily_summary.txt")

        os.makedirs(self.reports_dir, exist_ok=True)
        doc_dir = os.path.dirname(self.summary_doc_path)
        if doc_dir:
            os.makedirs(doc_dir, exist_ok=True)

    def parse_trade_ist_date(self, timestamp_str: str) -> str:
        """Extract YYYY-MM-DD in IST from trade timestamp."""
        try:
            dt = datetime.fromisoformat(timestamp_str)
            if dt.tzinfo is None:
                # If naive, assume IST as per MARkit operational clock
                dt = IST.localize(dt)
            else:
                dt = dt.astimezone(IST)
            return dt.strftime("%Y-%m-%d")
        except Exception:
            # Fallback string prefix slice
            return timestamp_str[:10]

    def get_trades_for_date(self, date_str: str) -> List[TradeRecord]:
        """Filter ledger trades executed on the given date (YYYY-MM-DD)."""
        matched = []
        for trade in self.ledger.trades:
            t_date = self.parse_trade_ist_date(trade.timestamp)
            if t_date == date_str:
                matched.append(trade)
        return matched

    def compute_daily_metrics(self, date_str: Optional[str] = None) -> DailyReport:
        """
        Compute comprehensive performance metrics and gather all trades for the given day.
        Defaults to current IST date if date_str is not provided.
        """
        now_ist = self.clock.now()
        target_date = date_str or now_ist.strftime("%Y-%m-%d")
        daily_trades = self.get_trades_for_date(target_date)

        buy_count = sum(1 for t in daily_trades if t.side == OrderSide.BUY)
        sell_count = sum(1 for t in daily_trades if t.side == OrderSide.SELL)

        # Profits and losses from closed (SELL) trades
        winning_trades = sum(1 for t in daily_trades if t.side == OrderSide.SELL and t.pnl > 0)
        losing_trades = sum(1 for t in daily_trades if t.side == OrderSide.SELL and t.pnl < 0)

        gross_profit = round(sum(t.pnl for t in daily_trades if t.side == OrderSide.SELL and t.pnl > 0), 2)
        gross_loss = round(abs(sum(t.pnl for t in daily_trades if t.side == OrderSide.SELL and t.pnl < 0)), 2)
        net_pnl = round(sum(t.pnl for t in daily_trades if t.side == OrderSide.SELL), 2)

        total_charges = round(sum(t.charges for t in daily_trades), 2)
        total_slippage = round(sum(t.slippage for t in daily_trades), 2)

        win_rate = round((winning_trades / sell_count * 100), 2) if sell_count > 0 else 0.0

        # Capital calculations
        # If target date matches today's session, use live ledger day start & current equity
        today_str = now_ist.strftime("%Y-%m-%d")
        if target_date == today_str:
            initial_amount = round(self.ledger.day_start_equity, 2)
            final_amount = round(self.ledger.total_equity, 2)
        else:
            # For past historical dates, reconstruct if possible or base on initial cash
            initial_amount = round(self.ledger.day_start_equity, 2)
            final_amount = round(initial_amount + net_pnl, 2)

        net_return_pct = (
            round(((final_amount - initial_amount) / initial_amount) * 100, 2)
            if initial_amount > 0
            else 0.0
        )

        trade_dicts = []
        for t in daily_trades:
            trade_dicts.append({
                "trade_id": t.trade_id,
                "timestamp": t.timestamp,
                "symbol": t.symbol,
                "side": t.side.value if isinstance(t.side, OrderSide) else str(t.side),
                "quantity": t.quantity,
                "requested_price": round(t.requested_price, 2),
                "filled_price": round(t.filled_price, 2),
                "slippage": round(t.slippage, 2),
                "charges": round(t.charges, 2),
                "net_amount": round(t.net_amount, 2),
                "pnl": round(t.pnl, 2),
                "reason": t.reason,
            })

        return DailyReport(
            date=target_date,
            initial_amount=initial_amount,
            final_amount=final_amount,
            total_trades=len(daily_trades),
            buy_trades=buy_count,
            sell_trades=sell_count,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate_pct=win_rate,
            profit=gross_profit,
            loss=gross_loss,
            net_pnl=net_pnl,
            total_charges=total_charges,
            total_slippage=total_slippage,
            net_return_pct=net_return_pct,
            trades=trade_dicts,
            generated_at=now_ist.isoformat(),
        )

    def generate_markdown_report(self, report: DailyReport) -> str:
        """
        Format a single-day comprehensive Markdown report with all trade parameters and KPIs.
        """
        pnl_symbol = "+" if report.net_pnl > 0 else ""
        lines = [
            f"# 📊 MARkit Daily Trading Session Report",
            f"**Session Date**: {report.date} | **Generated At**: {report.generated_at} (IST)",
            "",
            "## 1. Executive Performance Summary",
            "",
            "| Parameter | Value | Description |",
            "| :--- | :--- | :--- |",
            f"| **Initial Amount** | ₹{report.initial_amount:,.2f} | Starting portfolio equity at market open |",
            f"| **Final Amount** | ₹{report.final_amount:,.2f} | Ending portfolio equity at market close |",
            f"| **Net Realized P&L** | **{pnl_symbol}₹{report.net_pnl:,.2f}** | Realized profit/loss after Indian charges |",
            f"| **Net Session Return** | {pnl_symbol}{report.net_return_pct:.2f}% | Percentage return on daily capital |",
            f"| **Total Trades Executed** | {report.total_trades} | Total buy and sell fills |",
            f"| **Order Breakdown** | {report.buy_trades} BUY / {report.sell_trades} SELL | Intraday round-trip positions |",
            f"| **Win Rate** | {report.win_rate_pct:.1f}% ({report.winning_trades} Win / {report.losing_trades} Loss) | Closed trade profitability ratio |",
            f"| **Gross Realized Profit** | ₹{report.profit:,.2f} | Sum of profitable closed trades |",
            f"| **Gross Realized Loss** | ₹{report.loss:,.2f} | Sum of unprofitable closed trades |",
            f"| **Total Indian Friction** | ₹{report.total_charges:,.2f} | Statutory STT, GST, Exchange & SEBI fees |",
            f"| **Execution Slippage** | ₹{report.total_slippage:,.2f} | Modeled 0.05% market execution drift |",
            "",
            "## 2. Daily Summary Log Line (Master Record)",
            "```text",
            f"{report.date} -- {report.initial_amount:.2f} -- {report.final_amount:.2f} -- {report.total_trades} -- {report.profit:.2f} -- {report.loss:.2f}",
            "```",
            "",
            "## 3. Detailed Trade Execution Log (All Parameters)",
            "",
        ]

        if not report.trades:
            lines.append("*No trades executed during this session.*")
        else:
            lines.extend([
                "| Trade ID | Time | Symbol | Side | Qty | Req. Price | Fill Price | Slippage | Charges | Net Cash Flow | Realized P&L | Strategy & Reason |",
                "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
            ])
            for t in report.trades:
                time_str = t["timestamp"].split("T")[1][:8] if "T" in t["timestamp"] else t["timestamp"]
                pnl_str = f"₹{t['pnl']:+,.2f}" if t["side"] == "SELL" else "—"
                lines.append(
                    f"| `{t['trade_id']}` | {time_str} | **{t['symbol']}** | `{t['side']}` | {t['quantity']} | "
                    f"₹{t['requested_price']:.2f} | ₹{t['filled_price']:.2f} | ₹{t['slippage']:.2f} | ₹{t['charges']:.2f} | "
                    f"₹{t['net_amount']:.2f} | {pnl_str} | {t['reason']} |"
                )

        lines.extend([
            "",
            "---",
            "*Report auto-generated by MARkit Autonomous Indian Stock Trading Desk.*",
        ])

        return "\n".join(lines) + "\n"

    def update_common_summary_document(self, report: DailyReport) -> str:
        """
        Maintain common document appending exactly one line per day:
        Date -- Initial Amount -- Final Amount -- total number of trades -- Profit -- Loss

        Idempotent: If a line for the same date already exists, it updates that line in-place,
        ensuring only one single line is kept per day without duplicates.
        """
        line_content = (
            f"{report.date} -- {report.initial_amount:.2f} -- {report.final_amount:.2f} -- "
            f"{report.total_trades} -- {report.profit:.2f} -- {report.loss:.2f}"
        )

        existing_lines: List[str] = []
        if os.path.exists(self.summary_doc_path):
            with open(self.summary_doc_path, "r", encoding="utf-8") as f:
                existing_lines = [l.rstrip("\r\n") for l in f.readlines()]

        header_found = False
        updated_lines: List[str] = []
        date_prefix = f"{report.date} --"
        date_replaced = False

        for line in existing_lines:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("Date -- Initial Amount"):
                header_found = True
                updated_lines.append(self.SUMMARY_HEADER)
                continue

            if stripped.startswith(date_prefix):
                # Update existing entry for today
                updated_lines.append(line_content)
                date_replaced = True
            else:
                updated_lines.append(line)

        # Prepend header if not found
        if not header_found:
            updated_lines.insert(0, self.SUMMARY_HEADER)

        # Append new date line if not already replaced
        if not date_replaced:
            updated_lines.append(line_content)

        final_text = "\n".join(updated_lines) + "\n"
        with open(self.summary_doc_path, "w", encoding="utf-8") as f:
            f.write(final_text)

        logger.info(f"Updated common summary document at {self.summary_doc_path} for date {report.date}")
        return line_content

    def generate_and_save(self, date_str: Optional[str] = None) -> Tuple[DailyReport, str, str]:
        """
        Compute daily metrics, write detailed markdown & JSON reports, and update master document.
        Returns (report_object, markdown_file_path, json_file_path).
        """
        report = self.compute_daily_metrics(date_str)

        # 1. Write Markdown report
        md_filename = f"trade_report_{report.date}.md"
        md_filepath = os.path.join(self.reports_dir, md_filename)
        md_content = self.generate_markdown_report(report)
        with open(md_filepath, "w", encoding="utf-8") as f:
            f.write(md_content)

        # 2. Write JSON report
        json_filename = f"trade_report_{report.date}.json"
        json_filepath = os.path.join(self.reports_dir, json_filename)
        with open(json_filepath, "w", encoding="utf-8") as f:
            json.dump(asdict(report), f, indent=2)

        # 3. Update common summary document
        self.update_common_summary_document(report)

        logger.info(f"Generated daily report for {report.date}: {md_filepath}")
        return report, md_filepath, json_filepath

    def get_summary_document_content(self) -> str:
        """Return the raw text content of the common summary document."""
        if not os.path.exists(self.summary_doc_path):
            return self.SUMMARY_HEADER + "\n"
        with open(self.summary_doc_path, "r", encoding="utf-8") as f:
            return f.read()

    def list_reports(self) -> List[Dict]:
        """List all generated daily reports in the reports directory."""
        if not os.path.exists(self.reports_dir):
            return []

        results = []
        for fname in sorted(os.listdir(self.reports_dir), reverse=True):
            if fname.startswith("trade_report_") and fname.endswith(".json"):
                fpath = os.path.join(self.reports_dir, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    results.append({
                        "date": data.get("date"),
                        "total_trades": data.get("total_trades"),
                        "net_pnl": data.get("net_pnl"),
                        "profit": data.get("profit"),
                        "loss": data.get("loss"),
                        "json_file": fname,
                        "md_file": fname.replace(".json", ".md"),
                    })
                except Exception as e:
                    logger.warning(f"Could not parse report {fpath}: {e}")
        return results
