"""
Integration tests for the Knowledge Base Search API.
These tests run against the live standalone stack.
"""
import pytest
import requests
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

BASE_URL = os.getenv("API_URL", "http://localhost:8010/api/v1")
API_KEY = os.getenv("API_KEY", "dev-key-12345")

@pytest.fixture
def auth_headers():
    return {"X-API-Key": API_KEY}

def test_health_check():
    """Verify that the health check endpoint returns 200 and expected components."""
    response = requests.get(f"{BASE_URL}/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "components" in data
    assert "postgresql" in data["components"]
    assert "meilisearch" in data["components"]
    assert "qdrant" in data["components"]

def test_search_unauthorized():
    """Verify that search returns 401 without an API key."""
    response = requests.post(f"{BASE_URL}/search", json={"query": "test"})
    assert response.status_code == 401
    assert response.json()["status"] == "error"
    assert response.json()["error"]["code"] == "AUTH_ERROR"

def test_basic_search(auth_headers):
    """Verify that a basic search returns success."""
    payload = {
        "query": "postgresql",
        "limit": 5
    }
    response = requests.post(f"{BASE_URL}/search", json=payload, headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "data" in data
    assert "results" in data["data"]

def test_search_pagination(auth_headers):
    """Verify that pagination offset works correctly."""
    payload = {
        "query": "postgresql",
        "limit": 1,
        "offset": 0
    }
    # Get first result
    resp1 = requests.post(f"{BASE_URL}/search", json=payload, headers=auth_headers)
    assert resp1.status_code == 200
    doc1 = resp1.json()["data"]["results"][0]["doc_id"]
    
    # Get second result
    payload["offset"] = 1
    resp2 = requests.post(f"{BASE_URL}/search", json=payload, headers=auth_headers)
    assert resp2.status_code == 200
    if len(resp2.json()["data"]["results"]) > 0:
        doc2 = resp2.json()["data"]["results"][0]["doc_id"]
        assert doc1 != doc2

def test_search_filtering(auth_headers):
    """Verify that metadata filtering works."""
    payload = {
        "query": "postgresql",
        "filters": {
            "classification": "internal"
        }
    }
    response = requests.post(f"{BASE_URL}/search", json=payload, headers=auth_headers)
    assert response.status_code == 200
    for result in response.json()["data"]["results"]:
        assert result["classification"] == "internal"

if __name__ == "__main__":
    pytest.main([__file__])
