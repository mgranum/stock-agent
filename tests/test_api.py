import asyncio

import httpx
import pandas as pd

from src.api.app import create_app
from src.company_detail_query import CompanyDetailQuery


def _query():
    prices = pd.DataFrame(
        {
            "open": [100.0, 101.0],
            "high": [102.0, 103.0],
            "low": [99.0, 100.0],
            "close": [101.0, 102.0],
            "adjusted_close": [101.0, 102.0],
            "volume": [1000.0, 1200.0],
        },
        index=pd.to_datetime(["2026-08-06", "2026-08-07"]),
    )
    return CompanyDetailQuery(
        lambda *_args, **_kwargs: prices,
        lambda ticker: "NVIDIA Corporation",
    )


def _get(app, path, params=None):
    async def request():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.get(path, params=params)

    return asyncio.run(request())


def test_health_preserves_environment(monkeypatch):
    monkeypatch.setenv("STOCK_AGENT_ENV", "test")
    response = _get(create_app(_query()), "/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "environment": "test"}


def test_company_detail_contract():
    response = _get(
        create_app(_query()),
        "/api/stocks/nvda",
        params={"period": "1u"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ticker"] == "NVDA"
    assert body["company_name"] == "NVIDIA Corporation"
    assert body["period"] == "1u"
    assert body["candles"][-1]["close"] == 102.0


def test_invalid_period_is_422():
    response = _get(
        create_app(_query()),
        "/api/stocks/NVDA",
        params={"period": "2m"},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Ugyldig periode"
