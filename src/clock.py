"""
Indian Stock Market Clock & Operational Lifecycle State Machine.
Enforces official NSE/BSE timings (Asia/Kolkata):
- 09:00 - 09:15 IST: Pre-market briefing & watchlist generation
- 09:15 - 15:15 IST: Active Market Trading (BUY/SELL allowed)
- 15:15 - 15:30 IST: Intraday Auto Square-Off Window (Only closing open positions)
- 15:30 - 16:00 IST: Post-market review & day PnL lock
- 16:00 - 09:00 IST (and Weekends): Off-hours research mode (Trading locked)
"""

from datetime import datetime, time
from enum import Enum
import logging
from typing import Optional, Tuple
import pytz

logger = logging.getLogger(__name__)

IST = pytz.timezone("Asia/Kolkata")


class MarketState(str, Enum):
    PRE_MARKET_BRIEFING = "PRE_MARKET_BRIEFING"
    ACTIVE_MARKET = "ACTIVE_MARKET"
    AUTO_SQUAREOFF = "AUTO_SQUAREOFF"
    POST_MARKET_REVIEW = "POST_MARKET_REVIEW"
    OFF_HOURS_RESEARCH = "OFF_HOURS_RESEARCH"


class MarketClock:
    def __init__(self, timezone_str: str = "Asia/Kolkata"):
        self.tz = pytz.timezone(timezone_str)

    def now(self) -> datetime:
        """Return the current localized time in Indian Standard Time (IST)."""
        return datetime.now(self.tz)

    def get_market_state(self, dt: Optional[datetime] = None) -> MarketState:
        """
        Determine the current state of the Indian market.
        """
        current_dt = dt or self.now()
        if current_dt.tzinfo is None:
            current_dt = self.tz.localize(current_dt)
        else:
            current_dt = current_dt.astimezone(self.tz)

        # Saturday = 5, Sunday = 6
        if current_dt.weekday() in (5, 6):
            return MarketState.OFF_HOURS_RESEARCH

        t = current_dt.time()

        # 09:00 to 09:15 IST
        if time(9, 0) <= t < time(9, 15):
            return MarketState.PRE_MARKET_BRIEFING

        # 09:15 to 15:15 IST
        if time(9, 15) <= t < time(15, 15):
            return MarketState.ACTIVE_MARKET

        # 15:15 to 15:30 IST
        if time(15, 15) <= t < time(15, 30):
            return MarketState.AUTO_SQUAREOFF

        # 15:30 to 16:00 IST
        if time(15, 30) <= t < time(16, 0):
            return MarketState.POST_MARKET_REVIEW

        # 16:00 to 09:00 IST
        return MarketState.OFF_HOURS_RESEARCH

    def is_trading_allowed(self, dt: Optional[datetime] = None) -> Tuple[bool, str]:
        """
        Check whether order entry (BUY) is allowed right now.
        Returns (is_allowed, reason_description).
        """
        state = self.get_market_state(dt)
        current_dt = dt or self.now()
        if current_dt.weekday() in (5, 6):
            return False, "Market is closed on weekends (Saturday & Sunday)."

        if state == MarketState.ACTIVE_MARKET:
            return True, "Market is open for active trading (09:15 - 15:15 IST)."
        elif state == MarketState.AUTO_SQUAREOFF:
            return False, "Market is in Auto Square-Off window (15:15 - 15:30 IST). New orders are blocked."
        elif state == MarketState.PRE_MARKET_BRIEFING:
            return False, "Pre-market briefing window (09:00 - 09:15 IST). Orders open at 09:15 AM IST."
        elif state == MarketState.POST_MARKET_REVIEW:
            return False, "Post-market review window (15:30 - 16:00 IST). Market is closed."
        else:
            return False, "Off-hours research mode (16:00 - 09:00 IST). Only financial research permitted."

    def is_squareoff_window(self, dt: Optional[datetime] = None) -> bool:
        """Return True if within the 15:15 - 15:30 IST intraday square-off window."""
        return self.get_market_state(dt) == MarketState.AUTO_SQUAREOFF

    def is_research_only(self, dt: Optional[datetime] = None) -> bool:
        """Return True if trading is locked and only research is permissible."""
        state = self.get_market_state(dt)
        return state in (
            MarketState.OFF_HOURS_RESEARCH,
            MarketState.PRE_MARKET_BRIEFING,
            MarketState.POST_MARKET_REVIEW,
        )
