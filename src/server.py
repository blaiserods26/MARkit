"""
FastAPI Server & Real-Time Trading Desk Backend.
Exposes endpoints for portfolio state, market data, agent thought logs,
research summaries, and manual simulation controls.
"""

from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import datetime
import os
from typing import Dict, List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.agent import ActionType, TradingAgent
from src.clock import MarketClock
from src.ledger import OrderSide, VirtualLedger
from src.market_data import MarketDataProvider
from src.research import NewsResearcher

# Initialize core singletons
market_data_provider = MarketDataProvider()
virtual_ledger = VirtualLedger(initial_cash=10000.0, persistence_path="data/ledger.json")
market_clock = MarketClock()
news_researcher = NewsResearcher()
trading_agent = TradingAgent(
    ledger=virtual_ledger,
    market_data=market_data_provider,
    clock=market_clock,
    researcher=news_researcher,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initial startup log
    trading_agent.log_thought(
        thought="MARkit Trading Engine initialized. Paper capital: ₹10,000.00 INR. Ready.",
        action="SYSTEM_INIT",
    )
    yield


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
    for sym in virtual_ledger.positions.keys():
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
        return FileResponse(index_path)
    return HTMLResponse("<h1>MARkit Trading Server is Running</h1>")
