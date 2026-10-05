"""
FastAPI Server & Real-Time Trading Desk Backend.
Exposes endpoints for portfolio state, market data, agent thought logs,
research summaries, and manual simulation controls.
"""

import asyncio
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import datetime
import logging
import os
from typing import Dict, List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.agent import ActionType, TradingAgent
from src.clock import MarketClock
from src.gemini_rotator import GeminiKeyRotator
from src.ledger import OrderSide, VirtualLedger
from src.market_data import MarketDataProvider
from src.research import NewsResearcher

logger = logging.getLogger(__name__)

# Initialize core singletons
market_data_provider = MarketDataProvider()
virtual_ledger = VirtualLedger(initial_cash=10000.0, persistence_path="data/ledger.json")
market_clock = MarketClock()
news_researcher = NewsResearcher()
gemini_rotator = GeminiKeyRotator()
trading_agent = TradingAgent(
    ledger=virtual_ledger,
    market_data=market_data_provider,
    clock=market_clock,
    researcher=news_researcher,
    gemini_rotator=gemini_rotator,
)

# Autonomous trading loop controls
auto_trading_enabled: bool = True
cycle_interval_seconds: int = 15
_autonomous_task: Optional[asyncio.Task] = None


async def autonomous_trading_worker():
    """
    Background worker that runs autonomous trading cycles periodically.
    Enforces intraday limits, evaluates held positions for selling,
    and scans watchlist for buying up to remaining cash budget.
    """
    logger.info("Starting autonomous trading worker loop...")
    try:
        await asyncio.sleep(2)
    except asyncio.CancelledError:
        return

    while True:
        try:
            if auto_trading_enabled and not os.environ.get("PYTEST_CURRENT_TEST"):
                await asyncio.to_thread(trading_agent.execute_trade_cycle)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.exception(f"Exception in autonomous trading worker: {e}")
        try:
            await asyncio.sleep(cycle_interval_seconds)
        except asyncio.CancelledError:
            break


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _autonomous_task
    key_msg = (
        f"{gemini_rotator.key_count} keys active (random rotation)"
        if gemini_rotator.key_count > 0
        else "0 keys configured (heuristic engine active)"
    )
    trading_agent.log_thought(
        thought=f"MARkit Autonomous Trading Engine initialized. Paper capital: ₹{virtual_ledger.cash_balance:.2f} INR. Gemini AI: {key_msg}. Auto-Pilot: ACTIVE.",
        action="SYSTEM_INIT",
    )
    # Start autonomous trading background worker
    _autonomous_task = asyncio.create_task(autonomous_trading_worker())
    yield
    # Graceful shutdown
    if _autonomous_task:
        _autonomous_task.cancel()
        try:
            await _autonomous_task
        except asyncio.CancelledError:
            pass



app = FastAPI(title="MARkit Indian Stock Market Trading Agent", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure data directory exists
os.makedirs("data", exist_ok=True)
os.makedirs("static", exist_ok=True)


class ManualOrderRequest(BaseModel):
    symbol: str
    side: str
    quantity: int
    stop_loss: Optional[float] = None
    target: Optional[float] = None


@app.get("/api/status")
def get_system_status():
    now_ist = market_clock.now()
    market_state = market_clock.get_market_state(now_ist)
    can_trade, reason = market_clock.is_trading_allowed(now_ist)

    # Refresh held positions with live prices
    symbols = list(virtual_ledger.positions.keys())
    if symbols:
        quotes = market_data_provider.get_batch_quotes(symbols)
        virtual_ledger.update_live_prices({s: q.price for s, q in quotes.items()})

    return {
        "ist_time": now_ist.strftime("%Y-%m-%d %H:%M:%S IST"),
        "market_state": market_state.value,
        "can_trade": can_trade,
        "market_status_message": reason,
        "equity": virtual_ledger.total_equity,
        "cash_balance": virtual_ledger.cash_balance,
        "realized_pnl": virtual_ledger.realized_pnl,
        "daily_drawdown_pct": virtual_ledger.daily_drawdown_pct,
        "circuit_breaker_triggered": virtual_ledger.circuit_breaker_triggered,
        "open_positions_count": len(virtual_ledger.positions),
        "gemini_keys_configured": gemini_rotator.key_count,
        "auto_trading_enabled": auto_trading_enabled,
        "simulation_mode": market_clock.simulation_mode,
        "max_purchase_limit": virtual_ledger.get_max_purchase_value(),
    }


@app.get("/api/portfolio")
def get_portfolio():
    symbols = list(virtual_ledger.positions.keys())
    if symbols:
        quotes = market_data_provider.get_batch_quotes(symbols)
        virtual_ledger.update_live_prices({s: q.price for s, q in quotes.items()})

    positions_list = []
    for sym, pos in virtual_ledger.positions.items():
        positions_list.append({
            "symbol": pos.symbol,
            "quantity": pos.quantity,
            "average_entry_price": pos.average_entry_price,
            "current_price": pos.current_price,
            "market_value": pos.market_value,
            "unrealized_pnl": pos.unrealized_pnl,
            "unrealized_pnl_pct": pos.unrealized_pnl_pct,
            "stop_loss": pos.stop_loss,
            "target": pos.target,
            "opened_at": pos.opened_at,
        })

    trades_list = [
        {
            "trade_id": t.trade_id,
            "symbol": t.symbol,
            "side": t.side.value if isinstance(t.side, OrderSide) else t.side,
            "quantity": t.quantity,
            "requested_price": t.requested_price,
            "filled_price": t.filled_price,
            "slippage": t.slippage,
            "charges": t.charges,
            "net_amount": t.net_amount,
            "pnl": t.pnl,
            "reason": t.reason,
            "timestamp": t.timestamp,
        }
        for t in reversed(virtual_ledger.trades)
    ]

    return {
        "initial_cash": virtual_ledger.initial_cash,
        "cash_balance": virtual_ledger.cash_balance,
        "total_equity": virtual_ledger.total_equity,
        "realized_pnl": virtual_ledger.realized_pnl,
        "daily_drawdown_pct": virtual_ledger.daily_drawdown_pct,
        "circuit_breaker_triggered": virtual_ledger.circuit_breaker_triggered,
        "max_purchase_limit": virtual_ledger.get_max_purchase_value(),
        "positions": positions_list,
        "trades": trades_list,
    }


@app.get("/api/watchlist")
def get_watchlist():
    symbols = market_data_provider.get_nifty50_symbols()[:12]
    quotes_map = market_data_provider.get_batch_quotes(symbols)
    results = []
    for sym in symbols:
        q = quotes_map.get(sym)
        if q:
            results.append({
                "symbol": q.symbol,
                "price": q.price,
                "change_pct": q.change_pct,
                "day_high": q.day_high,
                "day_low": q.day_low,
                "volume": q.volume,
                "currency": q.currency,
            })
    return {"quotes": results}


@app.get("/api/research")
def get_research():
    if not trading_agent.pre_market_plan:
        macro = news_researcher.fetch_macro_news(limit=4)
        brief = news_researcher.generate_symbol_briefing("RELIANCE.NS")
        return {
            "macro_headlines": [m.title for m in macro],
            "sample_briefing": brief,
            "updated_at": datetime.now().isoformat(),
        }
    return trading_agent.pre_market_plan


@app.get("/api/thoughts")
def get_thought_logs(limit: int = 50):
    return {"thoughts": trading_agent.get_thought_logs(limit=limit)}


@app.post("/api/reports/generate")
def generate_report(date: Optional[str] = None):
    report, md_path, json_path = trading_agent.reporter.generate_and_save(date)
    return {
        "status": "SUCCESS",
        "report": asdict(report),
        "md_path": md_path,
        "json_path": json_path,
        "summary_line": f"{report.date} -- {report.initial_amount:.2f} -- {report.final_amount:.2f} -- {report.total_trades} -- {report.profit:.2f} -- {report.loss:.2f}",
    }


@app.get("/api/reports/daily")
def get_daily_report(date: Optional[str] = None):
    report = trading_agent.reporter.compute_daily_metrics(date)
    return asdict(report)


@app.get("/api/reports/summary-document")
def get_summary_document():
    content = trading_agent.reporter.get_summary_document_content()
    return {
        "document_path": trading_agent.reporter.summary_doc_path,
        "content": content,
        "lines": [l.strip() for l in content.splitlines() if l.strip()],
    }


@app.get("/api/reports/list")
def list_reports():
    return {"reports": trading_agent.reporter.list_reports()}


@app.get("/api/auto-trade/status")
def get_auto_trade_status():
    return {
        "auto_trading_enabled": auto_trading_enabled,
        "simulation_mode": market_clock.simulation_mode,
        "cycle_interval_seconds": cycle_interval_seconds,
        "max_purchase_limit": virtual_ledger.get_max_purchase_value(),
        "remaining_cash": virtual_ledger.cash_balance,
    }


@app.post("/api/auto-trade/toggle")
def toggle_auto_trade():
    global auto_trading_enabled
    auto_trading_enabled = not auto_trading_enabled
    state_str = "ENABLED" if auto_trading_enabled else "PAUSED"
    trading_agent.log_thought(
        thought=f"Auto-pilot autonomous trading {state_str} by operator.",
        action="AUTONOMOUS_TOGGLE",
    )
    return {"auto_trading_enabled": auto_trading_enabled}


@app.post("/api/simulation-mode/toggle")
def toggle_simulation_mode():
    market_clock.simulation_mode = not market_clock.simulation_mode
    state_str = "ENABLED (Active intraday paper trading)" if market_clock.simulation_mode else "DISABLED (Live NSE Clock)"
    trading_agent.log_thought(
        thought=f"Simulation mode {state_str}.",
        action="SIMULATION_TOGGLE",
    )
    return {"simulation_mode": market_clock.simulation_mode}


@app.post("/api/trigger-cycle")
def trigger_agent_cycle():
    result = trading_agent.execute_trade_cycle()
    return result


@app.post("/api/order")
def execute_manual_order(req: ManualOrderRequest):
    quote = market_data_provider.get_live_quote(req.symbol)
    if not quote:
        raise HTTPException(status_code=400, detail="Cannot fetch live market quote.")

    can_trade, reason = market_clock.is_trading_allowed()
    if not can_trade and req.side.upper() == "BUY":
        raise HTTPException(status_code=403, detail=f"Trading locked: {reason}")

    try:
        side = OrderSide.BUY if req.side.upper() == "BUY" else OrderSide.SELL
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid order side. Must be BUY or SELL.")

    if side == OrderSide.SELL and req.symbol not in virtual_ledger.positions:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot sell {req.symbol}: Stock was not purchased before. Intraday trading rules require purchasing before selling."
        )

    if side == OrderSide.BUY:
        max_allowed = virtual_ledger.get_max_purchase_value()
        order_val = quote.price * req.quantity
        if order_val > max_allowed:
            raise HTTPException(
                status_code=400,
                detail=f"Order value ₹{order_val:.2f} exceeds remaining allowable purchase limit of ₹{max_allowed:.2f}."
            )

    res = virtual_ledger.execute_order(
        symbol=req.symbol,
        side=side,
        quantity=req.quantity,
        current_price=quote.price,
        stop_loss=req.stop_loss,
        target=req.target,
        reason="Manual Paper Order",
    )
    trading_agent.log_thought(
        thought=f"Manual order request: {req.side} {req.quantity} {req.symbol} => {res.message}",
        action="MANUAL_ORDER",
        details=asdict(res.trade) if res.trade else {},
    )
    return {
        "status": res.status.value,
        "message": res.message,
        "filled_price": res.filled_price,
        "charges": res.charges,
    }


@app.post("/api/square-off-all")
def emergency_square_off():
    prices = {}
    for sym in list(virtual_ledger.positions.keys()):
        q = market_data_provider.get_live_quote(sym)
        if q:
            prices[sym] = q.price
    results = virtual_ledger.square_off_all(prices, reason="User Triggered Square-Off")
    trading_agent.log_thought(
        thought=f"Manual Square-off All executed for {len(results)} positions.",
        action="MANUAL_SQUAREOFF",
    )
    return {"squared_off_count": len(results)}


# Mount static files and root page
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def serve_index():
    index_path = os.path.join("static", "index.html")
    if os.path.exists(index_path):
        return FileResponse(
            index_path,
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )
    return HTMLResponse("<h1>MARkit Trading Server is Running</h1>")
