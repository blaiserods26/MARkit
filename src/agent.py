"""
Trading Agent Decision Engine & Execution Loop.
Autonomous trading agent with Gemini API / quantitative synthesis,
technical indicator engine (RSI, EMA, Trend), news sentiment scoring,
strict market clock state machine adherence, and live thought stream.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
import logging
import os
from typing import Dict, List, Optional
import pandas as pd

from src.clock import MarketClock, MarketState
from src.gemini_rotator import GeminiKeyRotator
from src.ledger import OrderSide, OrderStatus, TradeResult, VirtualLedger
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

    def evaluate_opportunity(self, symbol: str) -> AgentDecision:
        """
        Evaluate an opportunity by cross-referencing technical indicators and news sentiment.
        """
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

        action = ActionType.HOLD
        confidence = 0.5
        reasoning_parts = []
        stop_loss = None
        target_price = None

        # Bullish setup criteria
        # 1. Trend is Bullish or Sideways with Oversold RSI (< 45)
        # 2. News sentiment is not Bearish
        if trend == "BULLISH" and rsi < 65 and sentiment_rating != SentimentRating.BEARISH:
            action = ActionType.BUY
            confidence = 0.75 + (0.15 if sentiment_rating == SentimentRating.BULLISH else 0.0)
            stop_loss = round(price * 0.985, 2)  # 1.5% stop loss
            target_price = round(price * 1.03, 2)  # 3.0% profit target
            reasoning_parts.append(f"Bullish EMA crossover ({technicals['ema_fast']} > {technicals['ema_slow']}).")
            reasoning_parts.append(f"RSI healthy at {rsi}.")
            if sentiment_rating == SentimentRating.BULLISH:
                reasoning_parts.append(f"Positive news catalyst detected (Sentiment: +{sentiment_score}).")

        # Bearish / Overbought exit criteria
        elif trend == "BEARISH" or rsi > 75 or sentiment_rating == SentimentRating.BEARISH:
            action = ActionType.SELL
            confidence = 0.70 + (0.15 if sentiment_rating == SentimentRating.BEARISH else 0.0)
            reasoning_parts.append(f"Bearish signal: Trend={trend}, RSI={rsi}, Sentiment={sentiment_rating}.")

        else:
            action = ActionType.HOLD
            confidence = 0.5
            reasoning_parts.append(f"Neutral conditions: RSI={rsi}, Trend={trend}, Sentiment={sentiment_rating}.")

        # Calculate position sizing under 30% capital rule
        quantity = 0
        if action == ActionType.BUY and price > 0:
            max_capital_for_trade = self.ledger.total_equity * self.ledger.max_allocation_pct
            available_cash = self.ledger.cash_balance
            allocatable = min(max_capital_for_trade, available_cash * 0.95)
            quantity = int(allocatable // price)

        ai_thesis = None
        if action != ActionType.HOLD and self.gemini_rotator.key_count > 0:
            ai_thesis = self.generate_ai_thesis(symbol, technicals, research, action)
            if ai_thesis:
                reasoning_parts.append(f"AI Thesis: {ai_thesis}")

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
        """
        Ask Gemini using randomly rotated API keys to synthesize a crisp trade thesis.
        """
        if self.gemini_rotator.key_count == 0:
            return None

        headlines_text = "\n".join([f"- {h['title']}" for h in sentiment.get("headlines", [])[:3]])
        prompt = f"""You are a professional Indian Stock Market (NSE) Day Trader.
Analyze this setup for {symbol}:
- Proposed Action: {action.value}
- Current Price: ₹{technicals.get('current_price')}
- RSI (14): {technicals.get('rsi')}
- Trend: {technicals.get('trend')} (EMA9: ₹{technicals.get('ema_fast')}, EMA21: ₹{technicals.get('ema_slow')})
- News Sentiment: {sentiment.get('rating')} (Score: {sentiment.get('sentiment')})
Recent Headlines:
{headlines_text or "No immediate news"}

Provide a crisp 1-2 sentence trade thesis and risk observation. Avoid preamble."""
        return self.gemini_rotator.generate_text(prompt)


    def monitor_open_positions(self) -> List[TradeResult]:
        """
        Check active positions against stop-loss and profit targets.
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
                self.log_thought(
                    thought=f"STOP LOSS TRIGGERED for {symbol}: Current price ₹{current_price} <= Stop ₹{pos.stop_loss}",
                    action="RISK_EXIT",
                    details={"symbol": symbol, "price": current_price, "stop_loss": pos.stop_loss},
                )
                res = self.ledger.execute_order(
                    symbol=symbol,
                    side=OrderSide.SELL,
                    quantity=pos.quantity,
                    current_price=current_price,
                    reason=f"Stop Loss Hit at ₹{current_price}",
                )
                results.append(res)

            # Target hit
            elif pos.target and current_price >= pos.target:
                self.log_thought(
                    thought=f"PROFIT TARGET REACHED for {symbol}: Current price ₹{current_price} >= Target ₹{pos.target}",
                    action="TARGET_EXIT",
                    details={"symbol": symbol, "price": current_price, "target": pos.target},
                )
                res = self.ledger.execute_order(
                    symbol=symbol,
                    side=OrderSide.SELL,
                    quantity=pos.quantity,
                    current_price=current_price,
                    reason=f"Profit Target Reached at ₹{current_price}",
                )
                results.append(res)

        return results

    def execute_trade_cycle(self, mock_dt: Optional[datetime] = None) -> Dict:
        """
        Master decision loop executed every cycle.
        Respects Indian market clock and states.
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
                thought="15:15 IST reached: Intraday Auto Square-Off triggered. Closing all open positions.",
                action="AUTO_SQUAREOFF",
            )
            # Update quotes
            prices = {}
            for sym in self.ledger.positions.keys():
                q = self.market_data.get_live_quote(sym)
                if q:
                    prices[sym] = q.price
            squareoff_res = self.ledger.square_off_all(prices, reason="3:15 PM Intraday Auto Square-Off")
            cycle_result["status"] = "AUTO_SQUAREOFF"
            cycle_result["trades_executed"] = [asdict(r.trade) for r in squareoff_res if r.trade]
            return cycle_result

        # 2. If Off-Hours (Night or Weekend) or Pre-Market
        if not can_trade:
            self.log_thought(
                thought=f"Market is closed ({reason}). Execution locked. Running financial research mode.",
                action="OFF_HOURS_RESEARCH",
            )
            # Aggregate macro news and scan top 3 Nifty stocks for pre-market planning
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
            thought="Active Market Session: Monitoring open positions and scanning NIFTY 50 watchlist.",
            action="ACTIVE_SCAN",
        )

        # First monitor existing positions
        monitor_trades = self.monitor_open_positions()
        for tr in monitor_trades:
            if tr.trade:
                cycle_result["trades_executed"].append(asdict(tr.trade))

        # Check circuit breaker
        if self.ledger.circuit_breaker_triggered:
            self.log_thought(
                thought="Daily circuit breaker active. New trade entries halted for the session.",
                action="CIRCUIT_BREAKER_HALT",
            )
            cycle_result["status"] = "CIRCUIT_BREAKER_HALT"
            return cycle_result

        # Scan liquid watchlist for BUY opportunities if we have spare cash and < 3 open positions
        if len(self.ledger.positions) < 3 and self.ledger.cash_balance >= 1000.0:
            symbols = self.market_data.get_nifty50_symbols()[:8]
            for sym in symbols:
                if sym in self.ledger.positions:
                    continue  # Already holding

                decision = self.evaluate_opportunity(sym)
                self.log_thought(
                    thought=f"Evaluated {sym}: Action={decision.action.value}, Conf={decision.confidence:.2f}. {decision.reasoning}",
                    action="EVALUATION",
                    details={"symbol": sym, "action": decision.action.value, "confidence": decision.confidence},
                )

                if decision.action == ActionType.BUY and decision.confidence >= 0.75 and decision.quantity > 0:
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
                                thought=f"ORDER FILLED: Bought {decision.quantity} {sym} @ ₹{res.filled_price}. SL: ₹{decision.stop_loss}, TP: ₹{decision.target_price}",
                                action="EXECUTION_BUY",
                                details=asdict(res.trade),
                            )
                            cycle_result["trades_executed"].append(asdict(res.trade))
                            break  # Execute one high-conviction order per cycle

        cycle_result["status"] = "ACTIVE_MARKET_CYCLE_COMPLETE"
        self.last_cycle_summary = cycle_result
        return cycle_result
