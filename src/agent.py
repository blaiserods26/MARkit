"""
Trading Agent Decision Engine & Execution Loop.
Autonomous trading agent with Gemini API / quantitative synthesis,
technical indicator engine (RSI, EMA, Trend), news sentiment scoring,
strict market clock state machine adherence, and live thought stream.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
import json
import logging
import os
from typing import Dict, List, Optional
import pandas as pd

from src.clock import MarketClock, MarketState
from src.gemini_rotator import GeminiKeyRotator
from src.ledger import OrderSide, OrderStatus, Position, TradeResult, VirtualLedger
from src.market_data import MarketDataProvider, QuoteSnapshot
from src.research import NewsResearcher, SentimentRating

logger = logging.getLogger(__name__)


class ActionType(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    SQUARE_OFF = "SQUARE_OFF"


@dataclass
class AgentDecision:
    symbol: str
    action: ActionType
    confidence: float
    target_price: Optional[float] = None
    stop_loss: Optional[float] = None
    quantity: int = 0
    reasoning: str = ""
    ai_thesis: Optional[str] = None
    technicals: Dict = field(default_factory=dict)
    sentiment: Dict = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


def parse_ai_json(text: str) -> Optional[Dict]:
    """Extract and parse JSON from LLM response text, ignoring markdown backticks."""
    if not text:
        return None
    clean = text.strip()
    if clean.startswith("```"):
        lines = clean.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        clean = "\n".join(lines).strip()
    try:
        return json.loads(clean)
    except Exception:
        start = clean.find("{")
        end = clean.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(clean[start : end + 1])
            except Exception:
                pass
    return None


class TradingAgent:
    def __init__(
        self,
        ledger: VirtualLedger,
        market_data: MarketDataProvider,
        clock: MarketClock,
        researcher: NewsResearcher,
        gemini_rotator: Optional[GeminiKeyRotator] = None,
        gemini_api_key: Optional[str] = None,
    ):
        self.ledger = ledger
        self.market_data = market_data
        self.clock = clock
        self.researcher = researcher
        self.gemini_rotator = gemini_rotator or GeminiKeyRotator(
            keys=[gemini_api_key] if gemini_api_key else None
        )

        self.thought_logs: List[Dict] = []
        self.pre_market_plan: Dict = {}
        self.last_cycle_summary: Dict = {}


    def log_thought(self, thought: str, action: str = "ANALYSIS", details: Optional[Dict] = None) -> None:
        """Record structured agent thinking for real-time inspection."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "thought": thought,
            "action": action,
            "details": details or {},
        }
        self.thought_logs.append(entry)
        if len(self.thought_logs) > 500:
            self.thought_logs.pop(0)
        logger.info(f"[{action}] {thought}")

    def get_thought_logs(self, limit: int = 50) -> List[Dict]:
        return self.thought_logs[-limit:]

    def compute_technicals(self, symbol: str) -> Dict:
        """
        Calculate technical indicators: EMA 9, EMA 21, RSI 14, and Trend direction.
        """
        df = self.market_data.get_intraday_history(symbol, interval="5m", period="5d")
        if df.empty or len(df) < 25:
            # Fallback values if insufficient bars
            quote = self.market_data.get_live_quote(symbol)
            p = quote.price if quote else 1000.0
            return {
                "rsi": 50.0,
                "ema_fast": p,
                "ema_slow": p,
                "trend": "NEUTRAL",
                "volatility": 0.01,
            }

        close = df["Close"].copy()
        ema_fast = close.ewm(span=9, adjust=False).mean().iloc[-1]
        ema_slow = close.ewm(span=21, adjust=False).mean().iloc[-1]

        # RSI (14 period)
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss.replace(0, 1e-9)
        rsi_series = 100 - (100 / (1 + rs))
        rsi = float(rsi_series.iloc[-1]) if not pd.isna(rsi_series.iloc[-1]) else 50.0
        rsi = max(0.0, min(100.0, round(rsi, 2)))

        # Trend identification
        current_price = float(close.iloc[-1])
        if ema_fast > ema_slow and current_price >= ema_fast:
            trend = "BULLISH"
        elif ema_fast < ema_slow and current_price <= ema_fast:
            trend = "BEARISH"
        else:
            trend = "SIDEWAYS"

        volatility = round(float(close.pct_change().std()), 4)

        return {
            "rsi": rsi,
            "ema_fast": round(float(ema_fast), 2),
            "ema_slow": round(float(ema_slow), 2),
            "trend": trend,
            "volatility": volatility,
            "current_price": round(current_price, 2),
        }


    def generate_ai_decision(
        self,
        symbol: str,
        price: float,
        technicals: Dict,
        sentiment: Dict,
        is_held: bool,
        held_position: Optional[Position] = None,
    ) -> Optional[Dict]:
        """
        Query Gemini with full awareness of available cash, portfolio limits,
        and inventory of stocks purchased before.
        """
        if self.gemini_rotator.key_count == 0:
            return None

        available_cash = self.ledger.cash_balance
        total_equity = self.ledger.total_equity
        max_order_val = self.ledger.get_max_purchase_value()
        max_buy_qty = self.ledger.get_max_buy_quantity(price)

        held_summary = []
        for s, p in self.ledger.positions.items():
            held_summary.append(
                f"- {s}: {p.quantity} shares @ avg ₹{p.average_entry_price:.2f} (Current: ₹{p.current_price:.2f}, Unrealized P&L: ₹{p.unrealized_pnl:+.2f})"
            )
        held_text = "\n".join(held_summary) if held_summary else "None (No open positions)"

        headlines_text = "\n".join([f"- {h['title']}" for h in sentiment.get("headlines", [])[:3]])

        status_desc = (
            f"PURCHASED BEFORE: Holding {held_position.quantity} shares (Entry: ₹{held_position.average_entry_price:.2f}, P&L: ₹{held_position.unrealized_pnl:+.2f})"
            if (is_held and held_position)
            else "NOT PURCHASED BEFORE (Not currently held in portfolio)"
        )

        prompt = f"""You are an autonomous Indian Stock Market (NSE) Day Trader running an INTRADAY ONLY strategy.

FINANCIAL PORTFOLIO STATE:
- Total Portfolio Equity: ₹{total_equity:.2f} INR
- Available Cash Remaining: ₹{available_cash:.2f} INR
- Max Position Allocation Ceiling (30% max): ₹{round(total_equity * self.ledger.max_allocation_pct, 2):.2f} INR
- Maximum Allowable Purchase Value for this order: ₹{max_order_val:.2f} INR
- Maximum Buy Quantity within Budget: {max_buy_qty} shares at ₹{price:.2f}

CURRENTLY HELD POSITIONS (Stocks Purchased Before):
{held_text}

EVALUATING SYMBOL: {symbol}
- Current Market Price: ₹{price:.2f} INR
- Holding Status: {status_desc}
- Technical Indicators:
  * RSI (14): {technicals.get('rsi')}
  * Trend: {technicals.get('trend')} (EMA9: ₹{technicals.get('ema_fast')}, EMA21: ₹{technicals.get('ema_slow')})
  * Volatility: {technicals.get('volatility')}
- News Sentiment: {sentiment.get('rating')} (Score: {sentiment.get('sentiment')})
Recent Headlines:
{headlines_text or "No immediate news"}

STRICT TRADING RULES:
1. INTRADAY ONLY: All trades are intraday. All positions will be squared off before market close.
2. BUY RULES:
   - Allowed ONLY if the stock is NOT currently held.
   - The purchase order MUST be strictly limited to the remaining allowable value of ₹{max_order_val:.2f} (maximum {max_buy_qty} shares).
   - If max_buy_qty <= 0 or remaining cash is insufficient, you MUST choose HOLD.
3. SELL RULES:
   - You can ONLY SELL if the stock was PURCHASED BEFORE and is listed in Currently Held Positions above!
   - Under NO circumstances can you sell an unheld stock (no naked short selling).
   - If holding the stock, recommend SELL to take profit, cut loss, or if technical momentum breaks down.
4. DEBIT / CREDIT ACCOUNTING:
   - Purchasing debits cash by order cost + statutory charges.
   - Selling credits proceeds back into available cash.

Respond with a JSON object in this exact format:
{{
  "action": "BUY" | "SELL" | "HOLD",
  "quantity": <integer: 1 to {max_buy_qty} for BUY, or 1 to {held_position.quantity if (is_held and held_position) else 0} for SELL, or 0 for HOLD>,
  "confidence": <float between 0.0 and 1.0>,
  "target_price": <float target or null>,
  "stop_loss": <float stop loss or null>,
  "thesis": "<1-2 sentence trade thesis explicitly explaining how this fits within the remaining cash budget of ₹{available_cash:.2f} and intraday rules>"
}}"""

        raw_response = self.gemini_rotator.generate_text(prompt)
        if not raw_response:
            return None

        parsed = parse_ai_json(raw_response)
        if not parsed or not isinstance(parsed, dict):
            return None

        return parsed

    def evaluate_opportunity(
        self,
        symbol: str,
        is_held: Optional[bool] = None,
        held_position: Optional[Position] = None,
    ) -> AgentDecision:
        """
        Evaluate a stock setup with full financial context:
        - Stocks NOT purchased before can ONLY be bought or held (SELL strictly prohibited).
        - Stocks PURCHASED BEFORE can be sold or held.
        - Buy sizing strictly limited to remaining allowable cash budget.
        - Full financial metrics and constraints are dispatched to Gemini AI.
        """
        if is_held is None:
            is_held = symbol in self.ledger.positions
        if is_held and held_position is None:
            held_position = self.ledger.positions.get(symbol)

        quote = self.market_data.get_live_quote(symbol)
        if not quote:
            return AgentDecision(
                symbol=symbol,
                action=ActionType.HOLD,
                confidence=0.0,
                reasoning="Live quote unavailable",
            )

        technicals = self.compute_technicals(symbol)
        research = self.researcher.generate_symbol_briefing(symbol)

        price = quote.price
        rsi = technicals["rsi"]
        trend = technicals["trend"]
        sentiment_score = research["sentiment"]
        sentiment_rating = research["rating"]

        max_order_val = self.ledger.get_max_purchase_value()
        max_buy_qty = self.ledger.get_max_buy_quantity(price)
        available_cash = self.ledger.cash_balance

        # Baseline quantitative heuristics
        action = ActionType.HOLD
        confidence = 0.5
        reasoning_parts = []
        stop_loss = None
        target_price = None
        quantity = 0

        if is_held and held_position:
            # STOCK WAS PURCHASED BEFORE: Evaluate for SELL or HOLD
            pnl_pct = held_position.unrealized_pnl_pct
            if trend == "BEARISH" or rsi > 70 or sentiment_rating == SentimentRating.BEARISH or pnl_pct >= 2.5 or pnl_pct <= -1.5:
                action = ActionType.SELL
                confidence = 0.75 + (0.10 if trend == "BEARISH" else 0.0)
                quantity = held_position.quantity
                reasoning_parts.append(
                    f"Intraday SELL signal on held stock {symbol} (purchased before): Trend={trend}, RSI={rsi}, Sentiment={sentiment_rating}, Unrealized P&L={pnl_pct}%."
                )
            else:
                action = ActionType.HOLD
                confidence = 0.60
                quantity = 0
                reasoning_parts.append(
                    f"Holding {symbol} ({held_position.quantity} shares): Trend={trend}, RSI={rsi}, P&L={pnl_pct}%. Conditions stable."
                )
        else:
            # STOCK WAS NOT PURCHASED BEFORE: Evaluate for BUY or HOLD (CANNOT SELL!)
            if trend == "BULLISH" and rsi < 65 and sentiment_rating != SentimentRating.BEARISH:
                if max_buy_qty > 0 and available_cash >= price:
                    action = ActionType.BUY
                    confidence = 0.75 + (0.15 if sentiment_rating == SentimentRating.BULLISH else 0.0)
                    quantity = max_buy_qty
                    stop_loss = round(price * 0.985, 2)
                    target_price = round(price * 1.03, 2)
                    reasoning_parts.append(
                        f"Bullish intraday setup for {symbol}: Trend={trend}, RSI={rsi}. "
                        f"Purchase order sized to {quantity} shares (₹{quantity * price:.2f} <= ₹{max_order_val:.2f} remaining budget limit)."
                    )
                else:
                    action = ActionType.HOLD
                    confidence = 0.40
                    reasoning_parts.append(
                        f"Bullish signal for {symbol}, but purchase order halted: remaining cash ₹{available_cash:.2f} insufficient for share price ₹{price:.2f} under budget limits."
                    )
            else:
                action = ActionType.HOLD
                confidence = 0.50
                reasoning_parts.append(
                    f"Neutral/Bearish on unheld stock {symbol} (Trend={trend}, RSI={rsi}). Stock cannot be sold because it was not purchased before; holding."
                )

        # AI Synthesis with Gemini: Only synthesize when an action setup (BUY or SELL) is triggered
        ai_decision = None
        if action != ActionType.HOLD and self.gemini_rotator.key_count > 0:
            ai_decision = self.generate_ai_decision(
                symbol=symbol,
                price=price,
                technicals=technicals,
                sentiment=research,
                is_held=bool(is_held),
                held_position=held_position,
            )

        ai_thesis = None
        if ai_decision:
            ai_action_str = str(ai_decision.get("action", "")).upper()
            ai_conf = float(ai_decision.get("confidence", 0.7))
            ai_thesis = ai_decision.get("thesis", "")
            ai_target = ai_decision.get("target_price")
            ai_sl = ai_decision.get("stop_loss")
            ai_qty = int(ai_decision.get("quantity", 0))

            # Enforce strict domain guardrails:
            # 1. Cannot SELL unheld stock (stocks must be purchased before selling)
            if ai_action_str == "SELL" and not is_held:
                logger.warning(f"AI proposed SELL on unheld stock {symbol}. Blocked: stock was not purchased before.")
                ai_action_str = "HOLD"
                ai_qty = 0

            # 2. Cannot BUY if already held (avoid duplicate position bloat)
            if ai_action_str == "BUY" and is_held:
                ai_action_str = "HOLD"
                ai_qty = 0

            # 3. BUY quantity strictly capped by remaining allowable cash value
            if ai_action_str == "BUY":
                ai_qty = min(max_buy_qty, max(1, ai_qty if ai_qty > 0 else max_buy_qty))
                if ai_qty <= 0 or (ai_qty * price) > available_cash:
                    ai_action_str = "HOLD"
                    ai_qty = 0

            # 4. SELL quantity capped by held position inventory
            if ai_action_str == "SELL" and is_held and held_position:
                ai_qty = min(held_position.quantity, max(1, ai_qty if ai_qty > 0 else held_position.quantity))

            if ai_action_str in ("BUY", "SELL", "HOLD"):
                action = ActionType(ai_action_str)
                confidence = min(1.0, max(0.0, ai_conf))
                quantity = ai_qty
                if ai_target:
                    target_price = float(ai_target)
                if ai_sl:
                    stop_loss = float(ai_sl)
                reasoning_parts = [f"AI Thesis ({action.value}): {ai_thesis}"]
        elif ai_thesis is None and action != ActionType.HOLD:
            ai_thesis = f"Quantitative intraday {action.value} setup complying with remaining budget."

        return AgentDecision(
            symbol=symbol,
            action=action,
            confidence=min(1.0, round(confidence, 2)),
            target_price=target_price,
            stop_loss=stop_loss,
            quantity=quantity,
            reasoning=" ".join(reasoning_parts),
            ai_thesis=ai_thesis,
            technicals=technicals,
            sentiment=research,
        )

    def generate_ai_thesis(
        self, symbol: str, technicals: Dict, sentiment: Dict, action: ActionType
    ) -> Optional[str]:
        """Legacy helper for backward compatibility."""
        quote = self.market_data.get_live_quote(symbol)
        price = quote.price if quote else 1000.0
        dec = self.generate_ai_decision(symbol, price, technicals, sentiment, is_held=(symbol in self.ledger.positions))
        return dec.get("thesis") if dec else None

    def monitor_open_positions(self) -> List[TradeResult]:
        """
        Check active positions against stop-loss and profit targets.
        When stop/target triggers, proceeds are credited to cash.
        """
        results: List[TradeResult] = []
        for symbol, pos in list(self.ledger.positions.items()):
            quote = self.market_data.get_live_quote(symbol)
            if not quote:
                continue

            current_price = quote.price
            pos.current_price = current_price

            # Stop loss hit
            if pos.stop_loss and current_price <= pos.stop_loss:
                res = self.ledger.execute_order(
                    symbol=symbol,
                    side=OrderSide.SELL,
                    quantity=pos.quantity,
                    current_price=current_price,
                    reason=f"Stop Loss Hit at ₹{current_price}",
                )
                if res.status == OrderStatus.FILLED and res.trade:
                    self.log_thought(
                        thought=f"STOP LOSS HIT: Sold {pos.quantity} {symbol} @ ₹{current_price}. Cash Credited: ₹{res.trade.net_amount:.2f}. Realized P&L: ₹{res.trade.pnl:+.2f}. Updated Cash Remaining: ₹{self.ledger.cash_balance:.2f}.",
                        action="RISK_EXIT",
                        details=asdict(res.trade),
                    )
                    results.append(res)

            # Target hit
            elif pos.target and current_price >= pos.target:
                res = self.ledger.execute_order(
                    symbol=symbol,
                    side=OrderSide.SELL,
                    quantity=pos.quantity,
                    current_price=current_price,
                    reason=f"Profit Target Reached at ₹{current_price}",
                )
                if res.status == OrderStatus.FILLED and res.trade:
                    self.log_thought(
                        thought=f"PROFIT TARGET REACHED: Sold {pos.quantity} {symbol} @ ₹{current_price}. Cash Credited: ₹{res.trade.net_amount:.2f}. Realized P&L: ₹{res.trade.pnl:+.2f}. Updated Cash Remaining: ₹{self.ledger.cash_balance:.2f}.",
                        action="TARGET_EXIT",
                        details=asdict(res.trade),
                    )
                    results.append(res)

        return results

    def execute_trade_cycle(self, mock_dt: Optional[datetime] = None) -> Dict:
        """
        Master decision loop executed every cycle.
        Respects Indian market clock, intraday auto square-off,
        and strictly requires stocks to be purchased before selling.
        Debits cash on purchase and credits cash on selling.
        """
        current_dt = mock_dt or self.clock.now()
        market_state = self.clock.get_market_state(current_dt)
        can_trade, reason = self.clock.is_trading_allowed(current_dt)

        cycle_result = {
            "timestamp": current_dt.isoformat(),
            "market_state": market_state.value,
            "can_trade": can_trade,
            "status": "IDLE",
            "trades_executed": [],
            "research_brief": {},
        }

        # 1. If within Auto Square-Off window (15:15 - 15:30 IST)
        if self.clock.is_squareoff_window(current_dt):
            self.log_thought(
                thought="15:15 IST reached: Intraday Auto Square-Off triggered. Closing all open positions to eliminate overnight risk.",
                action="AUTO_SQUAREOFF",
            )
            prices = {}
            for sym in list(self.ledger.positions.keys()):
                q = self.market_data.get_live_quote(sym)
                if q:
                    prices[sym] = q.price
            squareoff_res = self.ledger.square_off_all(prices, reason="3:15 PM Intraday Auto Square-Off")
            cycle_result["status"] = "AUTO_SQUAREOFF"
            for r in squareoff_res:
                if r.trade:
                    self.log_thought(
                        thought=f"SQUARE-OFF FILLED: Sold {r.trade.quantity} {r.trade.symbol} @ ₹{r.filled_price}. Cash Credited: ₹{r.trade.net_amount:.2f}. PnL: ₹{r.trade.pnl:+.2f}. Final Cash Balance: ₹{self.ledger.cash_balance:.2f}.",
                        action="AUTO_SQUAREOFF_EXIT",
                        details=asdict(r.trade),
                    )
                    cycle_result["trades_executed"].append(asdict(r.trade))
            return cycle_result

        # 2. If Off-Hours (Night or Weekend) or Pre-Market
        if not can_trade:
            self.log_thought(
                thought=f"Market is closed ({reason}). Execution locked. Running financial research mode.",
                action="OFF_HOURS_RESEARCH",
            )
            macro = self.researcher.fetch_macro_news(limit=3)
            candidates = self.market_data.get_nifty50_symbols()[:3]
            plans = {}
            for sym in candidates:
                brief = self.researcher.generate_symbol_briefing(sym)
                plans[sym] = {
                    "rating": brief["rating"],
                    "sentiment": brief["sentiment"],
                    "headline": brief["headlines"][0]["title"] if brief["headlines"] else "None",
                }

            self.pre_market_plan = {
                "macro_headlines": [m.title for m in macro],
                "watchlist_sentiment": plans,
                "updated_at": current_dt.isoformat(),
            }

            cycle_result["status"] = "OFF_HOURS"
            cycle_result["research_brief"] = self.pre_market_plan
            return cycle_result

        # 3. Active Market Hours (09:15 - 15:15 IST)
        self.log_thought(
            thought=f"Active Market Session: Remaining Cash: ₹{self.ledger.cash_balance:.2f} INR (Max Order Budget: ₹{self.ledger.get_max_purchase_value():.2f}). Monitoring positions and scanning watchlist.",
            action="ACTIVE_SCAN",
            details={
                "cash_balance": self.ledger.cash_balance,
                "total_equity": self.ledger.total_equity,
                "max_purchase_limit": self.ledger.get_max_purchase_value(),
                "open_positions": list(self.ledger.positions.keys()),
            },
        )

        # Step 3A: Monitor stop-loss and profit targets on existing positions
        monitor_trades = self.monitor_open_positions()
        for tr in monitor_trades:
            if tr.trade:
                cycle_result["trades_executed"].append(asdict(tr.trade))

        # Step 3B: Evaluate currently held positions (purchased before) for AI / technical SELL signals
        for sym, pos in list(self.ledger.positions.items()):
            decision = self.evaluate_opportunity(sym, is_held=True, held_position=pos)
            self.log_thought(
                thought=f"Evaluated held position {sym}: Action={decision.action.value}, Conf={decision.confidence:.2f}. {decision.reasoning}",
                action="POSITION_EVALUATION",
                details={"symbol": sym, "action": decision.action.value, "confidence": decision.confidence},
            )
            if decision.action == ActionType.SELL and decision.confidence >= 0.65:
                quote = self.market_data.get_live_quote(sym)
                price = quote.price if quote else pos.current_price
                sell_qty = decision.quantity if decision.quantity > 0 else pos.quantity
                res = self.ledger.execute_order(
                    symbol=sym,
                    side=OrderSide.SELL,
                    quantity=sell_qty,
                    current_price=price,
                    reason=f"AI/Technical Intraday Exit: {decision.reasoning}",
                )
                if res.status == OrderStatus.FILLED and res.trade:
                    self.log_thought(
                        thought=f"CASH CREDITED: Credited ₹{res.trade.net_amount:.2f} from selling {sell_qty} {sym} @ ₹{res.filled_price}. Realized P&L: ₹{res.trade.pnl:+.2f}. Updated Cash Balance: ₹{self.ledger.cash_balance:.2f}.",
                        action="EXECUTION_SELL",
                        details=asdict(res.trade),
                    )
                    cycle_result["trades_executed"].append(asdict(res.trade))

        # Step 3C: Check circuit breaker
        if self.ledger.circuit_breaker_triggered:
            self.log_thought(
                thought="Daily circuit breaker active (drawdown reached limit). New trade entries halted for the session.",
                action="CIRCUIT_BREAKER_HALT",
            )
            cycle_result["status"] = "CIRCUIT_BREAKER_HALT"
            return cycle_result

        # Step 3D: Scan liquid watchlist for BUY opportunities if capital available and < 3 open positions
        if len(self.ledger.positions) < 3 and self.ledger.cash_balance >= 300.0:
            symbols = self.market_data.get_nifty50_symbols()[:6]
            for sym in symbols:
                if sym in self.ledger.positions:
                    continue  # Already purchased before; skip to avoid duplicate entries

                decision = self.evaluate_opportunity(sym, is_held=False, held_position=None)
                self.log_thought(
                    thought=f"Evaluated {sym}: Action={decision.action.value}, Conf={decision.confidence:.2f}. Sizing: {decision.quantity} shares. {decision.reasoning}",
                    action="EVALUATION",
                    details={
                        "symbol": sym,
                        "action": decision.action.value,
                        "confidence": decision.confidence,
                        "quantity": decision.quantity,
                    },
                )

                if decision.action == ActionType.BUY and decision.confidence >= 0.70 and decision.quantity > 0:
                    quote = self.market_data.get_live_quote(sym)
                    if quote:
                        res = self.ledger.execute_order(
                            symbol=sym,
                            side=OrderSide.BUY,
                            quantity=decision.quantity,
                            current_price=quote.price,
                            stop_loss=decision.stop_loss,
                            target=decision.target_price,
                            reason=f"AI Trade Setup: {decision.reasoning}",
                        )
                        if res.status == OrderStatus.FILLED and res.trade:
                            self.log_thought(
                                thought=f"CASH DEBITED: Debited ₹{res.trade.net_amount:.2f} for purchasing {decision.quantity} {sym} @ ₹{res.filled_price}. Remaining Cash Balance: ₹{self.ledger.cash_balance:.2f} (Purchase order strictly limited to budget ceiling). SL: ₹{decision.stop_loss}, TP: ₹{decision.target_price}.",
                                action="EXECUTION_BUY",
                                details=asdict(res.trade),
                            )
                            cycle_result["trades_executed"].append(asdict(res.trade))
                            break  # Execute one high-conviction order per cycle

        cycle_result["status"] = "ACTIVE_MARKET_CYCLE_COMPLETE"
        self.last_cycle_summary = cycle_result
        return cycle_result
