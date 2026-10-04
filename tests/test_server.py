from fastapi.testclient import TestClient
import pytest
from src.server import app

client = TestClient(app)

def test_api_status_endpoint():
    response = client.get("/api/status")
    assert response.status_code == 200
    data = response.json()
    assert "market_state" in data
    assert "ist_time" in data
    assert "can_trade" in data
    assert "equity" in data

def test_api_portfolio_endpoint():
    response = client.get("/api/portfolio")
    assert response.status_code == 200
    data = response.json()
    assert "cash_balance" in data
    assert "total_equity" in data
    assert "positions" in data
    assert "trades" in data

def test_api_watchlist_endpoint():
    response = client.get("/api/watchlist")
    assert response.status_code == 200
    data = response.json()
    assert "quotes" in data
    assert len(data["quotes"]) > 0

def test_api_research_endpoint():
    response = client.get("/api/research")
    assert response.status_code == 200
    data = response.json()
    assert "macro_headlines" in data or "watchlist_sentiment" in data

def test_api_trigger_cycle():
    response = client.post("/api/trigger-cycle")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
