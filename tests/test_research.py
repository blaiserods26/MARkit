import pytest
from src.research import NewsResearcher, SentimentScore, SentimentRating

def test_sentiment_analyzer_scoring():
    researcher = NewsResearcher()
    # Bullish text
    bullish_text = "Reliance Q2 profit surges 25% beating estimates, declared record dividend and strong revenue growth"
    score = researcher.evaluate_text_sentiment(bullish_text)
    assert score.rating == SentimentRating.BULLISH
    assert score.score > 0.2

    # Bearish text
    bearish_text = "Stock slumps 8% following SEBI probe, accounting fraud allegations, and severe quarterly loss"
    score = researcher.evaluate_text_sentiment(bearish_text)
    assert score.rating == SentimentRating.BEARISH
    assert score.score < -0.2

    # Neutral text
    neutral_text = "Board of Directors meeting scheduled on October 15 to discuss financial results"
    score = researcher.evaluate_text_sentiment(neutral_text)
    assert score.rating == SentimentRating.NEUTRAL

def test_fetch_symbol_news():
    researcher = NewsResearcher()
    articles = researcher.fetch_symbol_news("RELIANCE.NS", limit=5)
    assert len(articles) > 0
    assert articles[0].title
    assert articles[0].url

def test_fetch_macro_news():
    researcher = NewsResearcher()
    macro_articles = researcher.fetch_macro_news(limit=5)
    assert len(macro_articles) > 0

def test_generate_symbol_briefing():
    researcher = NewsResearcher()
    briefing = researcher.generate_symbol_briefing("TCS.NS")
    assert briefing["symbol"] == "TCS.NS"
    assert "sentiment" in briefing
    assert "article_count" in briefing
    assert "rating" in briefing
