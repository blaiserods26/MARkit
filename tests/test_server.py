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
    assert "gemini_keys_configured" in data

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


def test_api_report_endpoints():
    # 1. Trigger report generation
    gen_res = client.post("/api/reports/generate")
    assert gen_res.status_code == 200
    gen_data = gen_res.json()
    assert gen_data["status"] == "SUCCESS"
    assert "report" in gen_data
    assert "summary_line" in gen_data
    assert " -- " in gen_data["summary_line"]

    # 2. Get daily report
    daily_res = client.get("/api/reports/daily")
    assert daily_res.status_code == 200
    daily_data = daily_res.json()
    assert "total_trades" in daily_data
    assert "initial_amount" in daily_data
    assert "final_amount" in daily_data

    # 3. Get master summary document
    doc_res = client.get("/api/reports/summary-document")
    assert doc_res.status_code == 200
    doc_data = doc_res.json()
    assert "Date -- Initial Amount -- Final Amount -- total number of trades -- Profit -- Loss" in doc_data["content"]
    assert len(doc_data["lines"]) >= 2

    # 4. List reports
    list_res = client.get("/api/reports/list")
    assert list_res.status_code == 200
    list_data = list_res.json()
    assert "reports" in list_data
