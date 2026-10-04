"""
Financial News Research & Sentiment Analysis Tool.
Aggregates live Indian stock news from Google News RSS and Economic Times,
evaluates domain-tailored financial sentiment, and prepares pre-market briefings.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import logging
from typing import Dict, List, Optional
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)

# Canonical name map for top liquid NSE stocks
TICKER_NAME_MAP: Dict[str, str] = {
    "RELIANCE.NS": "Reliance Industries",
    "TCS.NS": "Tata Consultancy Services",
    "HDFCBANK.NS": "HDFC Bank",
    "INFY.NS": "Infosys",
    "ICICIBANK.NS": "ICICI Bank",
    "BHARTIARTL.NS": "Bharti Airtel",
    "SBIN.NS": "State Bank of India",
    "LICI.NS": "LIC India",
    "ITC.NS": "ITC Limited",
    "HINDUNILVR.NS": "Hindustan Unilever",
    "LT.NS": "Larsen & Toubro",
    "BAJFINANCE.NS": "Bajaj Finance",
    "MARUTI.NS": "Maruti Suzuki",
    "M&M.NS": "Mahindra & Mahindra",
    "KOTAKBANK.NS": "Kotak Mahindra Bank",
    "AXISBANK.NS": "Axis Bank",
    "TITAN.NS": "Titan Company",
    "ASIANPAINT.NS": "Asian Paints",
    "SUNPHARMA.NS": "Sun Pharma",
    "TATASTEEL.NS": "Tata Steel",
}

# Domain-specific financial sentiment lexicons
BULLISH_KEYWORDS = {
    "surge", "surges", "jump", "jumps", "rally", "rallies", "gain", "gains",
    "profit", "profits", "beat", "beats", "record", "growth", "outperform",
    "upgrade", "upgrades", "dividend", "acquisition", "expansion", "bullish",
    "breakout", "strong", "higher", "positive", "order win", "all-time high",
    "soar", "soars", "boost", "boosts", "deal", "contract"
}

BEARISH_KEYWORDS = {
    "slump", "slumps", "plunge", "plunges", "fall", "falls", "drop", "drops",
    "loss", "losses", "miss", "misses", "decline", "declines", "downgrade",
    "downgrades", "probe", "investigation", "fraud", "penalty", "fine",
    "default", "selloff", "bearish", "weak", "lower", "negative", "crisis",
    "crash", "warning", "caution", "headwind", "cut"
}


class SentimentRating(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


@dataclass
class NewsArticle:
    title: str
    url: str
    published_at: str
    source: str = "Google News"


@dataclass
class SentimentScore:
    score: float  # -1.0 to 1.0
    rating: SentimentRating
    bullish_signals: List[str] = field(default_factory=list)
    bearish_signals: List[str] = field(default_factory=list)


class NewsResearcher:
    def __init__(self, request_timeout: int = 8):
        self.request_timeout = request_timeout

    def _get_company_name(self, symbol: str) -> str:
        clean = symbol.upper().strip()
        return TICKER_NAME_MAP.get(clean, clean.replace(".NS", "").replace(".BO", ""))

    def evaluate_text_sentiment(self, text: str) -> SentimentScore:
        """
        Evaluate text against Indian financial market sentiment lexicons.
        """
        lower = text.lower()
        words = set(lower.replace(",", " ").replace(".", " ").replace(";", " ").split())

        found_bullish = [k for k in BULLISH_KEYWORDS if k in words or f" {k} " in f" {lower} "]
        found_bearish = [k for k in BEARISH_KEYWORDS if k in words or f" {k} " in f" {lower} "]

        bull_count = len(found_bullish)
        bear_count = len(found_bearish)
        total = bull_count + bear_count

        if total == 0:
            return SentimentScore(score=0.0, rating=SentimentRating.NEUTRAL)

        # Normalized sentiment score between -1.0 and 1.0
        score = round((bull_count - bear_count) / total, 2)

        if score > 0.15:
            rating = SentimentRating.BULLISH
        elif score < -0.15:
            rating = SentimentRating.BEARISH
        else:
            rating = SentimentRating.NEUTRAL

        return SentimentScore(
            score=score,
            rating=rating,
            bullish_signals=found_bullish,
            bearish_signals=found_bearish,
        )

    def fetch_symbol_news(self, symbol: str, limit: int = 5) -> List[NewsArticle]:
        """
        Fetch the latest live news headlines for an Indian stock symbol.
        """
        company_name = self._get_company_name(symbol)
        query = f"{company_name} share stock NSE"
        encoded = urllib.parse.quote(query)
        url = f"https://news.google.com/rss/search?q={encoded}&hl=en-IN&gl=IN&ceid=IN:en"

        articles: List[NewsArticle] = []
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
            with urllib.request.urlopen(req, timeout=self.request_timeout) as res:
                root = ET.fromstring(res.read())
                items = root.findall(".//item")
                for item in items[:limit]:
                    title_elem = item.find("title")
                    link_elem = item.find("link")
                    pub_elem = item.find("pubDate")

                    title = title_elem.text if title_elem is not None and title_elem.text else "No title"
                    link = link_elem.text if link_elem is not None and link_elem.text else ""
                    pub = pub_elem.text if pub_elem is not None and pub_elem.text else datetime.now().isoformat()

                    articles.append(NewsArticle(title=title, url=link, published_at=pub))
        except Exception as e:
            logger.warning(f"Error fetching news for {symbol}: {e}")

        return articles

    def fetch_macro_news(self, limit: int = 10) -> List[NewsArticle]:
        """
        Fetch overall Indian market / NIFTY macro news headlines from Economic Times RSS.
        """
        url = "https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms"
        articles: List[NewsArticle] = []
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
            with urllib.request.urlopen(req, timeout=self.request_timeout) as res:
                root = ET.fromstring(res.read())
                items = root.findall(".//item")
                for item in items[:limit]:
                    title_elem = item.find("title")
                    link_elem = item.find("link")
                    pub_elem = item.find("pubDate")

                    title = title_elem.text if title_elem is not None and title_elem.text else "No title"
                    link = link_elem.text if link_elem is not None and link_elem.text else ""
                    pub = pub_elem.text if pub_elem is not None and pub_elem.text else datetime.now().isoformat()

                    articles.append(NewsArticle(title=title, url=link, published_at=pub, source="Economic Times"))
        except Exception as e:
            logger.warning(f"Error fetching macro news: {e}")

        return articles

    def generate_symbol_briefing(self, symbol: str) -> Dict:
        """
        Compile research briefing and aggregate sentiment for a symbol.
        """
        articles = self.fetch_symbol_news(symbol, limit=6)
        if not articles:
            return {
                "symbol": symbol,
                "company_name": self._get_company_name(symbol),
                "article_count": 0,
                "sentiment": 0.0,
                "rating": SentimentRating.NEUTRAL.value,
                "headlines": [],
            }

        combined_text = " ".join([a.title for a in articles])
        sentiment = self.evaluate_text_sentiment(combined_text)

        return {
            "symbol": symbol,
            "company_name": self._get_company_name(symbol),
            "article_count": len(articles),
            "sentiment": sentiment.score,
            "rating": sentiment.rating.value,
            "bullish_signals": sentiment.bullish_signals,
            "bearish_signals": sentiment.bearish_signals,
            "headlines": [{"title": a.title, "url": a.url, "published": a.published_at} for a in articles],
        }
