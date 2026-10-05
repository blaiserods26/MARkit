"""
Trading Agent Decision Engine & Execution Loop.
Autonomous trading agent with Gemini API / quantitative synthesis,
technical indicator engine (RSI, EMA, Trend), news sentiment scoring,
strict market clock state machine adherence, and live thought stream.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, time
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
from src.reporter import DailyReport, DailyReportGenerator
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
        reporter: Optional[DailyReportGenerator] = None,
    ):
        self.ledger = ledger
        self.market_data = market_data
        self.clock = clock
        self.researcher = researcher
        self.gemini_rotator = gemini_rotator or GeminiKeyRotator(
            keys=[gemini_api_key] if gemini_api_key else None
        )
        self.reporter = reporter or DailyReportGenerator(ledger=self.ledger, clock=self.clock)

        self.thought_logs: List[Dict] = []
        self.pre_market_plan: Dict = {}
        self.last_cycle_summary: Dict = {}
        self.last_report_date: Optional[str] = None
        self.last_report: Optional[DailyReport] = None

        # Execution guardrails to eliminate friction and churn
        self.max_daily_trades: int = 5
        self.cooldown_seconds: int = 1200  # 20 minutes cooldown per symbol after exit
        self.min_dwell_seconds: int = 600  # 10 minutes minimum position holding time
        self.symbol_cooldowns: Dict[str, datetime] = {}


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
        Calculate technical indicators: EMA 9, EMA 21, RSI 14, 15m Trend, and Volume Ratio.
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
                "trend_15m": "SIDEWAYS",
                "vol_ratio": 1.0,
                "volatility": 0.01,
                "current_price": p,
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

        # 5m Trend identification
        current_price = float(close.iloc[-1])
        if ema_fast > ema_slow and current_price >= ema_fast:
            trend = "BULLISH"
        elif ema_fast < ema_slow and current_price <= ema_fast:
            trend = "BEARISH"
        else:
            trend = "SIDEWAYS"

        volatility = round(float(close.pct_change().std()), 4)

        # Volume moving average ratio (20-period)
        vol_ratio = 1.0
        if "Volume" in df.columns and len(df["Volume"]) >= 5:
            vol = df["Volume"]
            vol_ma = vol.rolling(window=min(20, len(vol))).mean().iloc[-1]
            last_vol = float(vol.iloc[-1])
            if vol_ma > 0:
                vol_ratio = round(last_vol / vol_ma, 2)

        # 15-minute trend confirmation
        trend_15m = "SIDEWAYS"
        try:
            df_15m = self.market_data.get_intraday_history(symbol, interval="15m", period="5d")
            if not df_15m.empty and len(df_15m) >= 15:
                c15 = df_15m["Close"]
                ema9_15 = c15.ewm(span=9, adjust=False).mean().iloc[-1]
                ema21_15 = c15.ewm(span=21, adjust=False).mean().iloc[-1]
                last_p15 = float(c15.iloc[-1])
                if ema9_15 > ema21_15 and last_p15 >= ema9_15:
                    trend_15m = "BULLISH"
                elif ema9_15 < ema21_15 and last_p15 <= ema9_15:
                    trend_15m = "BEARISH"
        except Exception:
            pass

        # ATR (Average True Range - 14 period)
        atr = round(max(1.0, current_price * 0.01), 2)
        if len(df) >= 15 and all(col in df.columns for col in ["High", "Low", "Close"]):
            try:
                high = df["High"]
                low = df["Low"]
                close_s = df["Close"]
                tr1 = high - low
                tr2 = (high - close_s.shift(1)).abs()
                tr3 = (low - close_s.shift(1)).abs()
                tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
                calculated_atr = float(tr.rolling(window=14).mean().iloc[-1])
                if not pd.isna(calculated_atr) and calculated_atr > 0:
                    atr = round(calculated_atr, 2)
            except Exception:
                pass

        # Institutional Open=Low / Open=High (OHL) pattern
        ohl_pattern = "NONE"
        open_price = current_price
        if len(df) >= 1 and all(col in df.columns for col in ["Open", "Low", "High"]):
            try:
                today_candles = df.iloc[-min(len(df), 12):]
                first_open = float(today_candles["Open"].iloc[0])
                day_low = float(today_candles["Low"].min())
                day_high = float(today_candles["High"].max())
                open_price = first_open
                if first_open > 0:
                    if (first_open - day_low) / first_open <= 0.0015:
                        ohl_pattern = "OPEN_LOW"
                    elif (day_high - first_open) / first_open <= 0.0015:
                        ohl_pattern = "OPEN_HIGH"
            except Exception:
                pass

        return {
            "rsi": rsi,
            "ema_fast": round(float(ema_fast), 2),
            "ema_slow": round(float(ema_slow), 2),
            "trend": trend,
            "trend_15m": trend_15m,
            "vol_ratio": vol_ratio,
            "volatility": volatility,
            "atr": atr,
            "ohl_pattern": ohl_pattern,
            "open_price": round(open_price, 2),
            "current_price": round(current_price, 2),
        }

    def get_market_regime(self) -> Dict:
        """
        Evaluate benchmark NIFTY 50 (^NSEI) 15m trend to protect against market-wide downturns.
        """
        try:
            df = self.market_data.get_intraday_history("^NSEI", interval="15m", period="5d")
            if df.empty or len(df) < 15:
                return {"trend": "NEUTRAL", "symbol": "^NSEI", "rsi": 50.0}
            c = df["Close"]
            ema9 = c.ewm(span=9, adjust=False).mean().iloc[-1]
            ema21 = c.ewm(span=21, adjust=False).mean().iloc[-1]
            p = float(c.iloc[-1])
            if ema9 > ema21 and p >= ema9:
                trend = "BULLISH"
            elif ema9 < ema21 and p <= ema21:
                trend = "BEARISH"
            else:
                trend = "SIDEWAYS"
            return {
                "trend": trend,
                "symbol": "^NSEI",
                "price": round(p, 2),
                "ema_fast": round(float(ema9), 2),
                "ema_slow": round(float(ema21), 2),
            }
        except Exception as e:
            logger.debug(f"Unable to fetch NIFTY 50 regime: {e}")
            return {"trend": "NEUTRAL", "symbol": "^NSEI"}


    def generate_ai_decision(
        self,
        symbol: str,
        price: float,
        technicals: Dict,
        sentiment: Dict,
        is_held: bool,
        held_position: Optional[Position] = None,
        allow_short: bool = False,
    ) -> Optional[Dict]:
        """
        Query Gemini with full awareness of available cash, portfolio limits,
        and inventory of stocks purchased before or shorted.
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
                f"- {s} ({p.side.value}): {p.quantity} shares @ avg ₹{p.average_entry_price:.2f} (Current: ₹{p.current_price:.2f}, Unrealized P&L: ₹{p.unrealized_pnl:+.2f})"
            )
        held_text = "\n".join(held_summary) if held_summary else "None (No open positions)"

        headlines_text = "\n".join([f"- {h['title']}" for h in sentiment.get("headlines", [])[:3]])

        status_desc = (
            f"CURRENTLY HELD ({held_position.side.value}): Holding {held_position.quantity} shares (Entry: ₹{held_position.average_entry_price:.2f}, P&L: ₹{held_position.unrealized_pnl:+.2f})"
            if (is_held and held_position)
            else "NOT CURRENTLY HELD (Not in portfolio)"
        )

        short_rule_desc = (
            "   - Market regime is BEARISH: You ARE permitted to recommend SELL on unheld stocks to enter an intraday short (MIS) position on breakdowns (sized up to max buy qty).\n"
            if allow_short
            else "   - You can ONLY SELL if the stock was PURCHASED BEFORE and is listed in Currently Held Positions above!\n   - Under NO circumstances can you sell an unheld stock when market regime is not bearish.\n"
        )

        prompt = f"""You are an autonomous Indian Stock Market (NSE) Day Trader running an INTRADAY ONLY strategy.

FINANCIAL PORTFOLIO STATE:
- Total Portfolio Equity: ₹{total_equity:.2f} INR
- Available Cash Remaining: ₹{available_cash:.2f} INR
- Max Position Allocation Ceiling (30% max): ₹{round(total_equity * self.ledger.max_allocation_pct, 2):.2f} INR
- Maximum Allowable Order Value for this position: ₹{max_order_val:.2f} INR
- Maximum Quantity within Budget: {max_buy_qty} shares at ₹{price:.2f}

CURRENTLY HELD POSITIONS:
{held_text}

EVALUATING SYMBOL: {symbol}
- Current Market Price: ₹{price:.2f} INR
- Holding Status: {status_desc}
- Technical Indicators:
  * RSI (14): {technicals.get('rsi')}
  * Trend: {technicals.get('trend')} (EMA9: ₹{technicals.get('ema_fast')}, EMA21: ₹{technicals.get('ema_slow')})
  * Volatility: {technicals.get('volatility')}
  * ATR: ₹{technicals.get('atr')}
  * OHL Pattern: {technicals.get('ohl_pattern')}
- News Sentiment: {sentiment.get('rating')} (Score: {sentiment.get('sentiment')})
Recent Headlines:
{headlines_text or "No immediate news"}

STRICT TRADING RULES:
1. INTRADAY ONLY: All trades are intraday. All positions will be squared off before market close.
2. BUY RULES:
   - If stock is not held, recommend BUY for strong bullish setups with target and stop loss.
   - If stock is held SHORT, recommend BUY to cover short.
   - Sizing strictly limited to {max_buy_qty} shares (order value <= ₹{max_order_val:.2f}).
3. SELL RULES:
{short_rule_desc}   - If holding a LONG position, recommend SELL to take profit or cut loss.
4. DEBIT / CREDIT ACCOUNTING:
   - Buying debits cash; selling long credits proceeds; opening short holds margin; covering short releases margin and settles P&L.

Respond with a JSON object in this exact format:
{{
  "action": "BUY" | "SELL" | "HOLD",
  "quantity": <integer: 1 to {max_buy_qty} for BUY/SHORT, or 1 to {held_position.quantity if (is_held and held_position) else 0} for exit, or 0 for HOLD>,
  "confidence": <float between 0.0 and 1.0>,
  "target_price": <float target or null>,
  "stop_loss": <float stop loss or null>,
  "thesis": "<1-2 sentence trade thesis explicitly explaining how this fits within the remaining budget and intraday rules>"
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
        current_dt: Optional[datetime] = None,
        allow_short: bool = False,
    ) -> AgentDecision:
        """
        Evaluate a stock setup with full financial context:
        - Stocks NOT purchased before can ONLY be bought or held (SELL strictly prohibited unless allow_short=True in bearish regime).
        - Stocks PURCHASED BEFORE can be sold or held.
        - Stocks SHORTED BEFORE can be covered (BUY) or held.
        - Buy sizing strictly limited to remaining allowable cash budget.
        - Enforces minimum dwell time to prevent whipsaw indicator jitter.
        - Enforces dynamic ATR stop-loss (1.5x ATR) and target (3.0x ATR) preserving >= 1:2 R:R.
        - Detects institutional Open=Low (bullish boost) and Open=High (bearish filter).
        - Multi-timeframe trend & volume confirmation.
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

        now_dt = current_dt or self.clock.now()
        dwell_seconds = 999999.0
        if is_held and held_position and held_position.opened_at:
            try:
                op_dt = datetime.fromisoformat(held_position.opened_at)
                if op_dt.tzinfo is None and now_dt.tzinfo is not None:
                    op_dt = self.clock.tz.localize(op_dt)
                elif op_dt.tzinfo is not None and now_dt.tzinfo is None:
                    now_dt = self.clock.tz.localize(now_dt)
                dwell_seconds = max(0.0, (now_dt - op_dt).total_seconds())
            except Exception:
                dwell_seconds = 999999.0

        if is_held and held_position:
            # STOCK WAS PURCHASED OR SHORTED BEFORE: Evaluate for EXIT or HOLD
            pnl_pct = held_position.unrealized_pnl_pct

            if held_position.side == OrderSide.BUY:
                # LONG POSITION EXIT LOGIC
                is_hard_stop = (pnl_pct <= -1.0) or (held_position.stop_loss is not None and price <= held_position.stop_loss)
                is_target_hit = (pnl_pct >= 2.5) or (held_position.target is not None and price >= held_position.target)

                # Prevent whipsaw / panic exits during minimum dwell time unless hard stop/target is hit
                if dwell_seconds < self.min_dwell_seconds and not (is_hard_stop or is_target_hit):
                    action = ActionType.HOLD
                    confidence = 0.65
                    quantity = 0
                    reasoning_parts.append(
                        f"Holding {symbol} ({held_position.quantity} shares): In minimum dwell window ({int(dwell_seconds)}s / {self.min_dwell_seconds}s). Protecting against whipsaw indicator jitter. P&L={pnl_pct:+.2f}%."
                    )
                elif is_hard_stop or is_target_hit or trend == "BEARISH" or sentiment_rating == SentimentRating.BEARISH:
                    action = ActionType.SELL
                    confidence = 0.80 + (0.10 if is_hard_stop else 0.0)
                    quantity = held_position.quantity
                    reasoning_parts.append(
                        f"Intraday SELL signal on held stock {symbol}: HardStop={is_hard_stop}, TargetHit={is_target_hit}, Trend={trend}, RSI={rsi}, Sentiment={sentiment_rating}, P&L={pnl_pct:+.2f}%."
                    )
                else:
                    action = ActionType.HOLD
                    confidence = 0.60
                    quantity = 0
                    reasoning_parts.append(
                        f"Holding {symbol} ({held_position.quantity} shares): Trend={trend}, RSI={rsi}, P&L={pnl_pct:+.2f}%. Position stable."
                    )
            else:
                # SHORT POSITION COVER LOGIC (held_position.side == OrderSide.SELL)
                is_hard_stop = (pnl_pct <= -1.0) or (held_position.stop_loss is not None and price >= held_position.stop_loss)
                is_target_hit = (pnl_pct >= 2.5) or (held_position.target is not None and price <= held_position.target)

                if dwell_seconds < self.min_dwell_seconds and not (is_hard_stop or is_target_hit):
                    action = ActionType.HOLD
                    confidence = 0.65
                    quantity = 0
                    reasoning_parts.append(
                        f"Holding SHORT {symbol} ({held_position.quantity} shares): In minimum dwell window ({int(dwell_seconds)}s / {self.min_dwell_seconds}s). P&L={pnl_pct:+.2f}%."
                    )
                elif is_hard_stop or is_target_hit or trend == "BULLISH" or sentiment_rating == SentimentRating.BULLISH:
                    action = ActionType.BUY
                    confidence = 0.80 + (0.10 if is_hard_stop else 0.0)
                    quantity = held_position.quantity
                    reasoning_parts.append(
                        f"Intraday SHORT COVER signal on {symbol}: HardStop={is_hard_stop}, TargetHit={is_target_hit}, Trend={trend}, RSI={rsi}, Sentiment={sentiment_rating}, P&L={pnl_pct:+.2f}%."
                    )
                else:
                    action = ActionType.HOLD
                    confidence = 0.60
                    quantity = 0
                    reasoning_parts.append(
                        f"Holding SHORT {symbol} ({held_position.quantity} shares): Trend={trend}, RSI={rsi}, P&L={pnl_pct:+.2f}%. Short position stable."
                    )
        else:
            # STOCK WAS NOT CURRENTLY HELD: Evaluate for BUY, SHORT (if allowed), or HOLD
            trend_15m = technicals.get("trend_15m", "SIDEWAYS")
            vol_ratio = technicals.get("vol_ratio", 1.0)
            atr = technicals.get("atr", round(max(1.0, price * 0.01), 2))
            ohl_pattern = technicals.get("ohl_pattern", "NONE")
            open_price = technicals.get("open_price", price)

            # Multi-timeframe trend & volume confirmation for BUY setup
            is_technical_bullish = (
                trend == "BULLISH"
                and ohl_pattern != "OPEN_HIGH"  # Filter out bearish institutional pressure
                and trend_15m in ("BULLISH", "SIDEWAYS")
                and (rsi < 65)
                and (vol_ratio >= 0.75)
                and sentiment_rating != SentimentRating.BEARISH
            )

            # Breakdown confirmation for SHORT setup (only if allow_short is True)
            is_technical_bearish = (
                allow_short
                and trend == "BEARISH"
                and ohl_pattern != "OPEN_LOW"  # Filter out bullish institutional support
                and trend_15m in ("BEARISH", "SIDEWAYS")
                and (rsi > 35)
                and (vol_ratio >= 0.75)
                and sentiment_rating != SentimentRating.BULLISH
            )

            if is_technical_bullish:
                # Dynamic ATR Stop-Loss (1.5x ATR) and Target (3.0x ATR)
                candidate_sl = round(price - 1.5 * atr, 2)
                candidate_target = round(price + 3.0 * atr, 2)
                if ohl_pattern == "OPEN_LOW" and open_price < price:
                    # Anchor stop loss above open price if tighter
                    candidate_sl = max(candidate_sl, round(open_price - 0.5, 2))

                risk = price - candidate_sl
                reward = candidate_target - price
                rr_ratio = reward / risk if risk > 0 else 0.0

                if rr_ratio >= 1.8 and max_buy_qty > 0 and available_cash >= price:
                    action = ActionType.BUY
                    base_conf = 0.75 + (0.15 if sentiment_rating == SentimentRating.BULLISH else 0.0)
                    if ohl_pattern == "OPEN_LOW":
                        base_conf += 0.10
                    confidence = min(0.95, base_conf)
                    quantity = max_buy_qty
                    stop_loss = candidate_sl
                    target_price = candidate_target
                    reasoning_parts.append(
                        f"Bullish setup for {symbol}: 5m Trend={trend}, 15m Trend={trend_15m}, VolRatio={vol_ratio}, RSI={rsi}, ATR=₹{atr:.2f}, OHL={ohl_pattern}. "
                        f"R:R={rr_ratio:.1f}:1. Sized to {quantity} shares (₹{quantity * price:.2f} <= ₹{max_order_val:.2f} budget limit)."
                    )
                else:
                    action = ActionType.HOLD
                    confidence = 0.40
                    reasoning_parts.append(
                        f"Bullish signal for {symbol}, but purchase order halted: R:R={rr_ratio:.1f}:1 or budget limit reached."
                    )
            elif is_technical_bearish:
                # Dynamic ATR Short Stop-Loss (1.5x ATR above price) and Target (3.0x ATR below price)
                candidate_sl = round(price + 1.5 * atr, 2)
                candidate_target = round(price - 3.0 * atr, 2)
                if ohl_pattern == "OPEN_HIGH" and open_price > price:
                    candidate_sl = min(candidate_sl, round(open_price + 0.5, 2))

                risk = candidate_sl - price
                reward = price - candidate_target
                rr_ratio = reward / risk if risk > 0 else 0.0

                if rr_ratio >= 1.8 and max_buy_qty > 0 and available_cash >= price:
                    action = ActionType.SELL
                    base_conf = 0.75 + (0.10 if ohl_pattern == "OPEN_HIGH" else 0.0)
                    confidence = min(0.95, base_conf)
                    quantity = max_buy_qty
                    stop_loss = candidate_sl
                    target_price = candidate_target
                    reasoning_parts.append(
                        f"Intraday Short setup (MIS) for {symbol}: 5m Trend={trend}, 15m={trend_15m}, VolRatio={vol_ratio}, RSI={rsi}, ATR=₹{atr:.2f}, OHL={ohl_pattern}. "
                        f"R:R={rr_ratio:.1f}:1. Sized to {quantity} shares."
                    )
                else:
                    action = ActionType.HOLD
                    confidence = 0.40
                    reasoning_parts.append(
                        f"Bearish breakdown on {symbol}, but short entry halted: R:R={rr_ratio:.1f}:1 or margin limit reached."
                    )
            else:
                action = ActionType.HOLD
                confidence = 0.50
                reasoning_parts.append(
                    f"Neutral/Consolidating on unheld stock {symbol} (5m={trend}, 15m={trend_15m}, RSI={rsi}, Vol={vol_ratio}, OHL={ohl_pattern}). Holding."
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
                allow_short=allow_short,
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
            # 1. Cannot SELL unheld stock unless shorting is allowed
            if ai_action_str == "SELL" and not is_held and not allow_short:
                logger.warning(f"AI proposed SELL on unheld stock {symbol}. Blocked: stock was not purchased before and shorting disabled.")
                ai_action_str = "HOLD"
                ai_qty = 0

            # 2. Cannot BUY if already held LONG (avoid duplicate position bloat)
            if ai_action_str == "BUY" and is_held and held_position and held_position.side == OrderSide.BUY:
                ai_action_str = "HOLD"
                ai_qty = 0

            # 3. BUY quantity strictly capped by remaining allowable cash value
            if ai_action_str == "BUY" and (not is_held or (held_position and held_position.side != OrderSide.SELL)):
                ai_qty = min(max_buy_qty, max(1, ai_qty if ai_qty > 0 else max_buy_qty))
                if ai_qty <= 0 or (ai_qty * price) > available_cash:
                    ai_action_str = "HOLD"
                    ai_qty = 0

            # 4. SELL quantity capped by held position inventory (for long exits) or margin (for short opens)
            if ai_action_str == "SELL":
                if is_held and held_position and held_position.side == OrderSide.BUY:
                    ai_qty = min(held_position.quantity, max(1, ai_qty if ai_qty > 0 else held_position.quantity))
                elif not is_held and allow_short:
                    ai_qty = min(max_buy_qty, max(1, ai_qty if ai_qty > 0 else max_buy_qty))
                    if ai_qty <= 0 or (ai_qty * price) > available_cash:
                        ai_action_str = "HOLD"
                        ai_qty = 0

            # 5. BUY quantity for short covering capped by held short quantity
            if ai_action_str == "BUY" and is_held and held_position and held_position.side == OrderSide.SELL:
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

    def monitor_open_positions(self, current_dt: Optional[datetime] = None) -> List[TradeResult]:
        """
        Check active positions against stop-loss, dynamic trailing stops, and profit targets.
        Supports both LONG positions (exited via SELL) and SHORT positions (exited via BUY).
        """
        results: List[TradeResult] = []
        now_dt = current_dt or self.clock.now()
        for symbol, pos in list(self.ledger.positions.items()):
            quote = self.market_data.get_live_quote(symbol)
            if not quote:
                continue

            current_price = quote.price
            pos.update_price(current_price)

            # Check dynamic trailing stop upgrade
            new_sl = pos.check_trailing_stop(activation_gain_pct=0.015, trail_distance_pct=0.0075)
            if new_sl:
                self.log_thought(
                    thought=f"TRAILING STOP ADJUSTED: {symbol} trailing stop set to ₹{new_sl:.2f} (Locking in profit).",
                    action="TRAILING_STOP_UPDATE",
                    details={"symbol": symbol, "trailing_stop": new_sl, "side": pos.side.value},
                )

            # LONG POSITION (side == OrderSide.BUY)
            if pos.side == OrderSide.BUY:
                if pos.stop_loss and current_price <= pos.stop_loss:
                    res = self.ledger.execute_order(
                        symbol=symbol,
                        side=OrderSide.SELL,
                        quantity=pos.quantity,
                        current_price=current_price,
                        reason=f"Stop/Trailing Stop Loss Hit at ₹{current_price} (SL: ₹{pos.stop_loss})",
                    )
                    if res.status == OrderStatus.FILLED and res.trade:
                        self.symbol_cooldowns[symbol] = now_dt
                        self.log_thought(
                            thought=f"STOP LOSS HIT: Sold {pos.quantity} {symbol} @ ₹{current_price}. Cash Credited: ₹{res.trade.net_amount:.2f}. Realized P&L: ₹{res.trade.pnl:+.2f}. Updated Cash Remaining: ₹{self.ledger.cash_balance:.2f}.",
                            action="RISK_EXIT",
                            details=asdict(res.trade),
                        )
                        results.append(res)
                elif pos.target and current_price >= pos.target:
                    res = self.ledger.execute_order(
                        symbol=symbol,
                        side=OrderSide.SELL,
                        quantity=pos.quantity,
                        current_price=current_price,
                        reason=f"Profit Target Reached at ₹{current_price} (TP: ₹{pos.target})",
                    )
                    if res.status == OrderStatus.FILLED and res.trade:
                        self.symbol_cooldowns[symbol] = now_dt
                        self.log_thought(
                            thought=f"PROFIT TARGET REACHED: Sold {pos.quantity} {symbol} @ ₹{current_price}. Cash Credited: ₹{res.trade.net_amount:.2f}. Realized P&L: ₹{res.trade.pnl:+.2f}. Updated Cash Remaining: ₹{self.ledger.cash_balance:.2f}.",
                            action="TARGET_EXIT",
                            details=asdict(res.trade),
                        )
                        results.append(res)

            # SHORT POSITION (side == OrderSide.SELL)
            else:
                if pos.stop_loss and current_price >= pos.stop_loss:
                    res = self.ledger.execute_order(
                        symbol=symbol,
                        side=OrderSide.BUY,
                        quantity=pos.quantity,
                        current_price=current_price,
                        reason=f"Short Stop Loss Hit at ₹{current_price} (SL: ₹{pos.stop_loss})",
                    )
                    if res.status == OrderStatus.FILLED and res.trade:
                        self.symbol_cooldowns[symbol] = now_dt
                        self.log_thought(
                            thought=f"SHORT STOP HIT: Covered {pos.quantity} {symbol} @ ₹{current_price}. Margin Released. Realized P&L: ₹{res.trade.pnl:+.2f}. Updated Cash Remaining: ₹{self.ledger.cash_balance:.2f}.",
                            action="RISK_EXIT",
                            details=asdict(res.trade),
                        )
                        results.append(res)
                elif pos.target and current_price <= pos.target:
                    res = self.ledger.execute_order(
                        symbol=symbol,
                        side=OrderSide.BUY,
                        quantity=pos.quantity,
                        current_price=current_price,
                        reason=f"Short Profit Target Reached at ₹{current_price} (TP: ₹{pos.target})",
                    )
                    if res.status == OrderStatus.FILLED and res.trade:
                        self.symbol_cooldowns[symbol] = now_dt
                        self.log_thought(
                            thought=f"SHORT PROFIT TARGET REACHED: Covered {pos.quantity} {symbol} @ ₹{current_price}. Margin Released. Realized P&L: ₹{res.trade.pnl:+.2f}. Updated Cash Remaining: ₹{self.ledger.cash_balance:.2f}.",
                            action="TARGET_EXIT",
                            details=asdict(res.trade),
                        )
                        results.append(res)

        return results

    def generate_ai_reflection(self, report: DailyReport) -> str:
        """Post-market reflection prompt analyzing friction, win rate, and strategic tuning."""
        if self.gemini_rotator.key_count == 0:
            return "AI key not configured; quantitative summary recorded."
        prompt = f"""You are the MARkit Indian Stock Trading Risk Officer.
Review the trading session performance for {report.date}:
- Initial Capital: ₹{report.initial_amount:.2f}
- Final Capital: ₹{report.final_amount:.2f}
- Net Realized P&L: ₹{report.net_pnl:+.2f} ({report.net_return_pct:+.2f}%)
- Total Trades: {report.total_trades} (Profit: ₹{report.profit:.2f}, Loss: ₹{report.loss:.2f})
- Win Rate: {report.win_rate_pct:.1f}% ({report.winning_trades} Win / {report.losing_trades} Loss)
- Total Charges: ₹{report.total_charges:.2f}, Slippage: ₹{report.total_slippage:.2f}

Provide a concise post-market analysis (3-4 bullet points):
1. Execution quality and friction impact.
2. What went well or poorly in strategy timing / selection.
3. 2 concrete risk management recommendations for tomorrow's market session."""
        try:
            res = self.gemini_rotator.generate_text(prompt)
            reflection = res.strip() if res else "AI post-market reflection complete."
            lessons_file = "reports/ai_lessons.json"
            os.makedirs("reports", exist_ok=True)
            existing_lessons = {}
            if os.path.exists(lessons_file):
                try:
                    with open(lessons_file, "r", encoding="utf-8") as f:
                        existing_lessons = json.load(f)
                except Exception:
                    existing_lessons = {}
            existing_lessons[report.date] = {
                "date": report.date,
                "net_pnl": report.net_pnl,
                "win_rate": report.win_rate_pct,
                "total_trades": report.total_trades,
                "reflection": reflection,
                "timestamp": datetime.now().isoformat(),
            }
            with open(lessons_file, "w", encoding="utf-8") as f:
                json.dump(existing_lessons, f, indent=2)
            return reflection
        except Exception as e:
            return f"AI reflection could not be generated: {e}"

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
            "daily_report": None,
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
                    self.symbol_cooldowns[r.trade.symbol] = current_dt
                    self.log_thought(
                        thought=f"SQUARE-OFF FILLED: Sold {r.trade.quantity} {r.trade.symbol} @ ₹{r.filled_price}. Cash Credited: ₹{r.trade.net_amount:.2f}. PnL: ₹{r.trade.pnl:+.2f}. Final Cash Balance: ₹{self.ledger.cash_balance:.2f}.",
                        action="AUTO_SQUAREOFF_EXIT",
                        details=asdict(r.trade),
                    )
                    cycle_result["trades_executed"].append(asdict(r.trade))
            return cycle_result

        # 2. Check for End-of-Day / Post-Market Report Generation
        today_str = current_dt.strftime("%Y-%m-%d")
        if not can_trade:
            # If after market close (post-market review or >= 15:30 on weekdays), ensure daily report is generated
            is_post_market = (
                market_state == MarketState.POST_MARKET_REVIEW
                or (current_dt.weekday() < 5 and current_dt.time() >= time(15, 30))
            )
            if is_post_market:
                current_day_trades = len(self.reporter.get_trades_for_date(today_str))
                if self.last_report_date != today_str or (
                    self.last_report and self.last_report.total_trades != current_day_trades
                ):
                    report, md_path, json_path = self.reporter.generate_and_save(today_str)
                    self.last_report_date = today_str
                    self.last_report = report
                    reflection = self.generate_ai_reflection(report)
                    self.log_thought(
                        thought=(
                            f"TRADING DAY CONCLUDED: Post-market daily report generated for {today_str}. "
                            f"Initial: ₹{report.initial_amount:.2f}, Final: ₹{report.final_amount:.2f}, "
                            f"Trades: {report.total_trades}, Profit: ₹{report.profit:.2f}, Loss: ₹{report.loss:.2f}, "
                            f"Net P&L: ₹{report.net_pnl:+.2f}. AI Reflection: {reflection[:100]}..."
                        ),
                        action="DAILY_REPORT_GENERATED",
                        details={
                            "date": report.date,
                            "report_md": md_path,
                            "report_json": json_path,
                            "total_trades": report.total_trades,
                            "net_pnl": report.net_pnl,
                            "ai_reflection": reflection,
                        },
                    )
                    cycle_result["daily_report"] = asdict(report)

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

        # Step 3A: Monitor stop-loss, dynamic trailing stops, and profit targets
        monitor_trades = self.monitor_open_positions(current_dt=current_dt)
        for tr in monitor_trades:
            if tr.trade:
                cycle_result["trades_executed"].append(asdict(tr.trade))

        # Step 3B: Evaluate currently held positions for AI / technical exit signals
        for sym, pos in list(self.ledger.positions.items()):
            decision = self.evaluate_opportunity(sym, is_held=True, held_position=pos, current_dt=current_dt)
            self.log_thought(
                thought=f"Evaluated held position {sym} ({pos.side.value}): Action={decision.action.value}, Conf={decision.confidence:.2f}. {decision.reasoning}",
                action="POSITION_EVALUATION",
                details={"symbol": sym, "action": decision.action.value, "confidence": decision.confidence, "side": pos.side.value},
            )
            # LONG EXIT: pos.side == OrderSide.BUY, exit via SELL
            if pos.side == OrderSide.BUY and decision.action == ActionType.SELL and decision.confidence >= 0.65:
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
                    self.symbol_cooldowns[sym] = current_dt
                    self.log_thought(
                        thought=f"CASH CREDITED: Credited ₹{res.trade.net_amount:.2f} from selling {sell_qty} {sym} @ ₹{res.filled_price}. Realized P&L: ₹{res.trade.pnl:+.2f}. Updated Cash Balance: ₹{self.ledger.cash_balance:.2f}.",
                        action="EXECUTION_SELL",
                        details=asdict(res.trade),
                    )
                    cycle_result["trades_executed"].append(asdict(res.trade))

            # SHORT COVER: pos.side == OrderSide.SELL, exit via BUY
            elif pos.side == OrderSide.SELL and decision.action == ActionType.BUY and decision.confidence >= 0.65:
                quote = self.market_data.get_live_quote(sym)
                price = quote.price if quote else pos.current_price
                buy_qty = decision.quantity if decision.quantity > 0 else pos.quantity
                res = self.ledger.execute_order(
                    symbol=sym,
                    side=OrderSide.BUY,
                    quantity=buy_qty,
                    current_price=price,
                    reason=f"AI/Technical Intraday Short Cover: {decision.reasoning}",
                )
                if res.status == OrderStatus.FILLED and res.trade:
                    self.symbol_cooldowns[sym] = current_dt
                    self.log_thought(
                        thought=f"SHORT COVERED: Bought {buy_qty} {sym} @ ₹{res.filled_price}. Margin Released. Realized P&L: ₹{res.trade.pnl:+.2f}. Updated Cash Balance: ₹{self.ledger.cash_balance:.2f}.",
                        action="EXECUTION_COVER",
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

        # Step 3D: Timing gates and daily trade limit check before scanning BUY / SHORT opportunities
        can_enter, entry_reason = self.clock.is_entry_allowed(current_dt)
        today_buys = [
            t for t in self.ledger.trades
            if t.timestamp.startswith(today_str) and t.side == OrderSide.BUY
        ]

        if not can_enter:
            self.log_thought(
                thought=f"ENTRY CUTOFF ACTIVE: {entry_reason}. Scanning for new positions halted.",
                action="ENTRY_CUTOFF_HALT",
            )
        elif len(today_buys) >= self.max_daily_trades:
            self.log_thought(
                thought=f"DAILY TRADE LIMIT REACHED: {len(today_buys)}/{self.max_daily_trades} orders executed today. Halting new entries to prevent friction bleed.",
                action="DAILY_LIMIT_HALT",
            )
        elif len(self.ledger.positions) < 3 and self.ledger.cash_balance >= 300.0:
            regime = self.get_market_regime()
            is_bearish = regime.get("trend") == "BEARISH"
            if is_bearish:
                self.log_thought(
                    thought="MARKET REGIME BEARISH: Benchmark NIFTY 50 (^NSEI) is trending down (EMA9 < EMA21). Enabling intraday short-selling (MIS) on breakdown leaders.",
                    action="REGIME_FILTER",
                    details=regime,
                )

            # Dynamic Nifty 50 RVOL and momentum screener
            symbols = self.market_data.screen_top_movers(limit=6)
            for sym in symbols:
                if sym in self.ledger.positions:
                    continue  # Already held; skip to avoid duplicate entries

                # Check symbol cooldown (20 minutes after last exit)
                if sym in self.symbol_cooldowns:
                    last_exit = self.symbol_cooldowns[sym]
                    cur_compare = current_dt
                    if last_exit.tzinfo is None and cur_compare.tzinfo is not None:
                        last_exit = self.clock.tz.localize(last_exit)
                    elif last_exit.tzinfo is not None and cur_compare.tzinfo is None:
                        cur_compare = self.clock.tz.localize(cur_compare)
                    elapsed_cd = (cur_compare - last_exit).total_seconds()
                    if elapsed_cd < self.cooldown_seconds:
                        self.log_thought(
                            thought=f"SYMBOL COOLDOWN ACTIVE: {sym} was exited {int(elapsed_cd)}s ago (< {self.cooldown_seconds}s). Skipping to prevent churn.",
                            action="COOLDOWN_SKIP",
                            details={"symbol": sym, "elapsed": elapsed_cd, "cooldown": self.cooldown_seconds},
                        )
                        continue

                decision = self.evaluate_opportunity(
                    sym,
                    is_held=False,
                    held_position=None,
                    current_dt=current_dt,
                    allow_short=is_bearish,
                )
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

                if decision.action == ActionType.BUY and not is_bearish and decision.confidence >= 0.70 and decision.quantity > 0:
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
                                thought=f"CASH DEBITED: Debited ₹{res.trade.net_amount:.2f} for purchasing {decision.quantity} {sym} @ ₹{res.filled_price}. Remaining Cash Balance: ₹{self.ledger.cash_balance:.2f}. SL: ₹{decision.stop_loss}, TP: ₹{decision.target_price}.",
                                action="EXECUTION_BUY",
                                details=asdict(res.trade),
                            )
                            cycle_result["trades_executed"].append(asdict(res.trade))
                            break  # Execute one high-conviction order per cycle

                elif decision.action == ActionType.SELL and is_bearish and decision.confidence >= 0.70 and decision.quantity > 0:
                    quote = self.market_data.get_live_quote(sym)
                    if quote:
                        res = self.ledger.execute_order(
                            symbol=sym,
                            side=OrderSide.SELL,
                            quantity=decision.quantity,
                            current_price=quote.price,
                            stop_loss=decision.stop_loss,
                            target=decision.target_price,
                            allow_short=True,
                            reason=f"Intraday Short Setup (MIS): {decision.reasoning}",
                        )
                        if res.status == OrderStatus.FILLED and res.trade:
                            self.log_thought(
                                thought=f"SHORT OPENED (MIS): Sold short {decision.quantity} {sym} @ ₹{res.filled_price}. Margin Held: ₹{res.trade.net_amount:.2f}. Remaining Cash Balance: ₹{self.ledger.cash_balance:.2f}. SL: ₹{decision.stop_loss}, TP: ₹{decision.target_price}.",
                                action="EXECUTION_SHORT",
                                details=asdict(res.trade),
                            )
                            cycle_result["trades_executed"].append(asdict(res.trade))
                            break  # Execute one high-conviction order per cycle

        cycle_result["status"] = "ACTIVE_MARKET_CYCLE_COMPLETE"
        self.last_cycle_summary = cycle_result
        return cycle_result

    def generate_daily_report(self, date_str: Optional[str] = None) -> DailyReport:
        """Manually trigger daily report generation and common master document update."""
        report, md_path, json_path = self.reporter.generate_and_save(date_str)
        self.last_report_date = report.date
        self.last_report = report
        reflection = self.generate_ai_reflection(report)
        self.log_thought(
            thought=(
                f"DAILY REPORT GENERATED on demand for {report.date}. "
                f"Initial: ₹{report.initial_amount:.2f}, Final: ₹{report.final_amount:.2f}, "
                f"Trades: {report.total_trades}, Profit: ₹{report.profit:.2f}, Loss: ₹{report.loss:.2f}, "
                f"Net P&L: ₹{report.net_pnl:+.2f}. Master record updated."
            ),
            action="MANUAL_REPORT_GENERATED",
            details={
                "date": report.date,
                "md_path": md_path,
                "json_path": json_path,
                "total_trades": report.total_trades,
                "net_pnl": report.net_pnl,
                "ai_reflection": reflection,
            },
        )
        return report

