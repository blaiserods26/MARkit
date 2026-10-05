"""
Paper Trading Ledger & Order Execution Simulator.
Tracks virtual portfolio, realistic slippage, Indian regulatory charges (STT, GST, SEBI, Stamp Duty),
position risk limits (30% max allocation), and daily drawdown circuit breakers (3%).
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
import json
import logging
import os
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(str, Enum):
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


@dataclass
class Position:
    symbol: str
    quantity: int
    average_entry_price: float
    current_price: float
    stop_loss: Optional[float] = None
    target: Optional[float] = None
    highest_price: float = 0.0
    opened_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def __post_init__(self):
        if self.highest_price <= 0:
            self.highest_price = max(self.current_price, self.average_entry_price)

    @property
    def market_value(self) -> float:
        return round(self.quantity * self.current_price, 2)

    @property
    def unrealized_pnl(self) -> float:
        return round(self.quantity * (self.current_price - self.average_entry_price), 2)

    @property
    def unrealized_pnl_pct(self) -> float:
        if self.average_entry_price <= 0:
            return 0.0
        return round(((self.current_price - self.average_entry_price) / self.average_entry_price) * 100, 2)

    def update_price(self, new_price: float) -> None:
        self.current_price = new_price
        if self.highest_price <= 0:
            self.highest_price = max(new_price, self.average_entry_price)
        else:
            self.highest_price = max(self.highest_price, new_price)

    def check_trailing_stop(self, activation_gain_pct: float = 0.015, trail_distance_pct: float = 0.0075) -> Optional[float]:
        """
        Dynamic trailing stop:
        Activates when unrealized gain reaches +1.5% from average entry.
        Trails the highest watermark price by 0.75%.
        Returns new stop_loss if updated, else None.
        """
        if self.highest_price <= 0 or self.average_entry_price <= 0:
            return None
        max_gain_pct = (self.highest_price - self.average_entry_price) / self.average_entry_price
        if max_gain_pct >= activation_gain_pct:
            new_sl = round(self.highest_price * (1.0 - trail_distance_pct), 2)
            if self.stop_loss is None or new_sl > self.stop_loss:
                self.stop_loss = new_sl
                return new_sl
        return None


@dataclass
class TradeRecord:
    trade_id: str
    symbol: str
    side: OrderSide
    quantity: int
    requested_price: float
    filled_price: float
    slippage: float
    charges: float
    net_amount: float
    pnl: float = 0.0
    reason: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class TradeResult:
    status: OrderStatus
    message: str
    trade: Optional[TradeRecord] = None
    filled_price: float = 0.0
    charges: float = 0.0


def calculate_indian_charges(side: OrderSide, turnover: float) -> float:
    """
    Calculate statutory transaction charges for Indian Intraday Equity:
    - STT: 0.025% on sell turnover
    - Exchange turnover charge (NSE): 0.00297%
    - SEBI turnover charge: 0.0001%
    - Stamp duty: 0.003% on buy turnover
    - GST: 18% on (Exchange turnover + SEBI charges)
    """
    stt = (turnover * 0.00025) if side == OrderSide.SELL else 0.0
    exchange_fee = turnover * 0.0000297
    sebi_fee = turnover * 0.000001
    stamp_duty = (turnover * 0.00003) if side == OrderSide.BUY else 0.0
    gst = (exchange_fee + sebi_fee) * 0.18

    total = stt + exchange_fee + sebi_fee + stamp_duty + gst
    return round(total, 2)


class VirtualLedger:
    def __init__(
        self,
        initial_cash: float = 10000.0,
        max_allocation_pct: float = 0.30,
        circuit_breaker_pct: float = 0.03,
        slippage_pct: float = 0.0005,
        persistence_path: str = "data/ledger.json",
    ):
        self.initial_cash = initial_cash
        self.cash_balance = initial_cash
        self.max_allocation_pct = max_allocation_pct
        self.circuit_breaker_pct = circuit_breaker_pct
        self.slippage_pct = slippage_pct
        self.persistence_path = persistence_path

        self.positions: Dict[str, Position] = {}
        self.trades: List[TradeRecord] = []
        self.realized_pnl: float = 0.0
        self.circuit_breaker_triggered: bool = False
        self.day_start_equity: float = initial_cash

        self._load()

    @property
    def total_equity(self) -> float:
        pos_val = sum(pos.market_value for pos in self.positions.values())
        return round(self.cash_balance + pos_val, 2)

    @property
    def daily_drawdown_pct(self) -> float:
        if self.day_start_equity <= 0:
            return 0.0
        drawdown = max(0.0, self.day_start_equity - self.total_equity)
        return round((drawdown / self.day_start_equity) * 100, 2)

    def get_max_purchase_value(self) -> float:
        """
        Maximum purchase value allowed for any new position:
        Strictly capped by the 30% allocation ceiling of total equity,
        and cannot exceed remaining cash balance (with 5% buffer for statutory charges).
        """
        max_by_equity = round(self.total_equity * self.max_allocation_pct, 2)
        max_by_cash = round(max(0.0, self.cash_balance * 0.95), 2)
        return round(min(max_by_equity, max_by_cash), 2)

    def get_max_buy_quantity(self, price: float) -> int:
        """Calculate maximum buyable shares of a stock given remaining allowable cash value."""
        if price <= 0:
            return 0
        return int(self.get_max_purchase_value() // price)

    def execute_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: int,
        current_price: float,
        stop_loss: Optional[float] = None,
        target: Optional[float] = None,
        reason: str = "",
    ) -> TradeResult:
        if quantity <= 0:
            return TradeResult(status=OrderStatus.REJECTED, message="Quantity must be greater than zero.")

        if current_price <= 0:
            return TradeResult(status=OrderStatus.REJECTED, message="Invalid stock price.")

        # Check circuit breaker
        if self.circuit_breaker_triggered or (self.daily_drawdown_pct >= self.circuit_breaker_pct * 100):
            self.circuit_breaker_triggered = True
            return TradeResult(
                status=OrderStatus.REJECTED,
                message=f"Circuit breaker triggered: Daily drawdown reached {self.daily_drawdown_pct:.2f}% (Limit: {self.circuit_breaker_pct * 100:.1f}%).",
            )

        # Apply realistic 0.05% slippage
        if side == OrderSide.BUY:
            filled_price = round(current_price * (1.0 + self.slippage_pct), 2)
        else:
            filled_price = round(current_price * (1.0 - self.slippage_pct), 2)

        slippage = round(abs(filled_price - current_price) * quantity, 2)
        turnover = filled_price * quantity
        charges = calculate_indian_charges(side, turnover)

        if side == OrderSide.BUY:
            # Enforce max 30% capital allocation per position
            max_allowed = self.total_equity * self.max_allocation_pct
            total_req = turnover + charges

            if turnover > max_allowed:
                return TradeResult(
                    status=OrderStatus.REJECTED,
                    message=f"Order exceeds max allocation limit of ₹{max_allowed:.2f} (Requested ₹{turnover:.2f}).",
                )

            if total_req > self.cash_balance:
                return TradeResult(
                    status=OrderStatus.REJECTED,
                    message=f"Insufficient funds. Required: ₹{total_req:.2f}, Available: ₹{self.cash_balance:.2f}.",
                )

            # Deduct cash
            self.cash_balance = round(self.cash_balance - total_req, 2)

            # Update or create position
            if symbol in self.positions:
                existing = self.positions[symbol]
                new_qty = existing.quantity + quantity
                new_avg = round(
                    ((existing.quantity * existing.average_entry_price) + turnover) / new_qty, 2
                )
                existing.quantity = new_qty
                existing.average_entry_price = new_avg
                existing.current_price = filled_price
                if stop_loss:
                    existing.stop_loss = stop_loss
                if target:
                    existing.target = target
            else:
                self.positions[symbol] = Position(
                    symbol=symbol,
                    quantity=quantity,
                    average_entry_price=filled_price,
                    current_price=filled_price,
                    stop_loss=stop_loss,
                    target=target,
                )

            trade = TradeRecord(
                trade_id=f"TRD-{len(self.trades) + 1:04d}",
                symbol=symbol,
                side=OrderSide.BUY,
                quantity=quantity,
                requested_price=current_price,
                filled_price=filled_price,
                slippage=slippage,
                charges=charges,
                net_amount=total_req,
                pnl=0.0,
                reason=reason,
            )
            self.trades.append(trade)
            self._save()

            return TradeResult(
                status=OrderStatus.FILLED,
                message=f"Bought {quantity} shares of {symbol} at ₹{filled_price}. Cash debited: ₹{total_req:.2f} (Charges: ₹{charges:.2f}). Remaining cash: ₹{self.cash_balance:.2f}.",
                trade=trade,
                filled_price=filled_price,
                charges=charges,
            )

        elif side == OrderSide.SELL:
            if symbol not in self.positions or self.positions[symbol].quantity < quantity:
                avail = self.positions[symbol].quantity if symbol in self.positions else 0
                return TradeResult(
                    status=OrderStatus.REJECTED,
                    message=f"Cannot sell {quantity} shares of {symbol}. Available position: {avail}. Stocks must be purchased before selling.",
                )

            pos = self.positions[symbol]
            cost_basis = pos.average_entry_price * quantity
            trade_pnl = round(turnover - cost_basis - charges, 2)
            net_credit = round(turnover - charges, 2)

            self.cash_balance = round(self.cash_balance + net_credit, 2)
            self.realized_pnl = round(self.realized_pnl + trade_pnl, 2)

            pos.quantity -= quantity
            if pos.quantity <= 0:
                del self.positions[symbol]

            trade = TradeRecord(
                trade_id=f"TRD-{len(self.trades) + 1:04d}",
                symbol=symbol,
                side=OrderSide.SELL,
                quantity=quantity,
                requested_price=current_price,
                filled_price=filled_price,
                slippage=slippage,
                charges=charges,
                net_amount=net_credit,
                pnl=trade_pnl,
                reason=reason,
            )
            self.trades.append(trade)

            # Check if circuit breaker tripped after loss
            if self.daily_drawdown_pct >= (self.circuit_breaker_pct * 100):
                self.circuit_breaker_triggered = True

            self._save()

            return TradeResult(
                status=OrderStatus.FILLED,
                message=f"Sold {quantity} shares of {symbol} at ₹{filled_price}. Cash credited: ₹{net_credit:.2f} (Charges: ₹{charges:.2f}). Net P&L: ₹{trade_pnl:.2f}. Updated cash: ₹{self.cash_balance:.2f}.",
                trade=trade,
                filled_price=filled_price,
                charges=charges,
            )

        return TradeResult(status=OrderStatus.REJECTED, message="Unsupported order side.")

    def square_off_all(self, current_prices: Dict[str, float], reason: str = "Auto Square-Off") -> List[TradeResult]:
        """Square off all active positions."""
        results: List[TradeResult] = []
        for symbol, pos in list(self.positions.items()):
            price = current_prices.get(symbol, pos.current_price)
            res = self.execute_order(
                symbol=symbol,
                side=OrderSide.SELL,
                quantity=pos.quantity,
                current_price=price,
                reason=reason,
            )
            results.append(res)
        return results

    def update_live_prices(self, current_prices: Dict[str, float]) -> None:
        """Update current price of all held positions."""
        for symbol, pos in self.positions.items():
            if symbol in current_prices:
                pos.current_price = current_prices[symbol]

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self.persistence_path) or ".", exist_ok=True)
        data = {
            "initial_cash": self.initial_cash,
            "cash_balance": self.cash_balance,
            "realized_pnl": self.realized_pnl,
            "circuit_breaker_triggered": self.circuit_breaker_triggered,
            "day_start_equity": self.day_start_equity,
            "positions": {
                sym: {
                    "symbol": p.symbol,
                    "quantity": p.quantity,
                    "average_entry_price": p.average_entry_price,
                    "current_price": p.current_price,
                    "stop_loss": p.stop_loss,
                    "target": p.target,
                    "opened_at": p.opened_at,
                    "highest_price": p.highest_price,
                }
                for sym, p in self.positions.items()
            },
            "trades": [
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
                for t in self.trades
            ],
        }
        with open(self.persistence_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def _load(self) -> None:
        if not os.path.exists(self.persistence_path):
            return
        try:
            with open(self.persistence_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.initial_cash = data.get("initial_cash", self.initial_cash)
            self.cash_balance = data.get("cash_balance", self.cash_balance)
            self.realized_pnl = data.get("realized_pnl", 0.0)
            self.circuit_breaker_triggered = data.get("circuit_breaker_triggered", False)
            self.day_start_equity = data.get("day_start_equity", self.initial_cash)

            self.positions = {}
            for sym, p in data.get("positions", {}).items():
                self.positions[sym] = Position(
                    symbol=p["symbol"],
                    quantity=p["quantity"],
                    average_entry_price=p["average_entry_price"],
                    current_price=p["current_price"],
                    stop_loss=p.get("stop_loss"),
                    target=p.get("target"),
                    highest_price=p.get("highest_price", p["current_price"]),
                    opened_at=p.get("opened_at", datetime.now().isoformat()),
                )

            self.trades = []
            for t in data.get("trades", []):
                self.trades.append(
                    TradeRecord(
                        trade_id=t["trade_id"],
                        symbol=t["symbol"],
                        side=OrderSide(t["side"]),
                        quantity=t["quantity"],
                        requested_price=t["requested_price"],
                        filled_price=t["filled_price"],
                        slippage=t["slippage"],
                        charges=t["charges"],
                        net_amount=t["net_amount"],
                        pnl=t.get("pnl", 0.0),
                        reason=t.get("reason", ""),
                        timestamp=t.get("timestamp", datetime.now().isoformat()),
                    )
                )
        except Exception as e:
            logger.exception(f"Failed to load ledger from {self.persistence_path}: {e}")
