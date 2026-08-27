"""
Unit tests for src/extract/fetch_coingecko.py

Run with: pytest tests/
These tests mock the CoinGecko API so they run offline and don't hit rate limits.
"""

import json
from datetime import date
from pathlib import Path

import pytest
import requests

from src.extract import fetch_coingecko


SAMPLE_RESPONSE = [
    {
        "id": "bitcoin",
        "symbol": "btc",
        "name": "Bitcoin",
        "current_price": 65000.0,
        "market_cap": 1280000000000,
        "market_cap_rank": 1,
        "total_volume": 30000000000,
        "high_24h": 65500.0,
        "low_24h": 64000.0,
        "price_change_24h": 500.0,
        "price_change_percentage_24h": 0.77,
        "price_change_percentage_7d_in_currency": 3.2,
        "circulating_supply": 19700000,
        "total_supply": 21000000,
        "ath": 73000.0,
        "ath_date": "2024-03-14T00:00:00.000Z",
        "last_updated": "2026-08-27T00:00:00.000Z",
    }
]


def test_fetch_market_data_success(mocker):
    mock_response = mocker.Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = SAMPLE_RESPONSE
    mock_response.raise_for_status.return_value = None

    mocker.patch("requests.get", return_value=mock_response)

    data = fetch_coingecko.fetch_market_data(top_n=1)

    assert len(data) == 1
    assert data[0]["id"] == "bitcoin"


def test_fetch_market_data_raises_after_retries(mocker):
    mock_response = mocker.Mock()
    mock_response.status_code = 500
    mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("server error")

    mocker.patch("requests.get", return_value=mock_response)
    mocker.patch("time.sleep")  # skip real backoff delay in tests

    with pytest.raises(RuntimeError):
        fetch_coingecko.fetch_market_data(top_n=1)


def test_save_local_writes_expected_structure(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    run_date = date(2026, 8, 27)

    out_path = fetch_coingecko.save_local(SAMPLE_RESPONSE, run_date)

    assert out_path.exists()
    with open(out_path) as f:
        payload = json.load(f)

    assert payload["record_count"] == 1
    assert payload["records"][0]["symbol"] == "btc"
    assert out_path == Path("data/raw/2026-08-27/coingecko_markets.json")
