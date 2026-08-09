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


def _post(app, path, json):
    async def request():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.post(path, json=json)

    return asyncio.run(request())


class PresentationStub:
    meta = {
        "status": "fresh",
        "environment": "test",
        "model_version": "test-v1",
        "built_at": "2026-08-08T08:00:00+00:00",
        "snapshot_date": "2026-08-08",
        "message": None,
    }

    def today(self):
        return {
            "meta": self.meta,
            "attention": [],
            "owned": [],
            "watchlist": [],
            "candidates": [],
        }

    def company_context(self, ticker):
        return {
            "meta": self.meta,
            "company_name": "NVIDIA Corporation",
            "recommendation": "KJØP / ØK",
            "score": 78,
        }

    def explore(self):
        return {"meta": self.meta, "watchlist_ranking": [], "candidates": []}

    def positions(self):
        return {"meta": self.meta, "positions": []}

    def watchlists(self):
        return {"meta": self.meta, "watchlists": []}

    def search(self, query, limit=20):
        return {"meta": self.meta, "query": query, "results": []}

    def refresh_status(self):
        return {
            "environment": "test",
            "status": "ok",
            "status_label": "OK",
            "updated_at": "2026-08-08 10:00",
            "updated_at_source": "refresh_state",
            "last_successful_date": "2026-08-08",
            "last_error_count": 0,
        }

    def model_status(self):
        return {"meta": self.meta, "refresh": self.refresh_status()}

    def model_data(self):
        return {
            "meta": self.meta,
            "refresh": self.refresh_status(),
            "market_regime": {},
            "strategy_profiles": [],
            "research_ideas": {},
            "snapshots": {},
            "discovery_journal": {},
        }

    def chat(self, question, **_context):
        return {"meta": self.meta, "answer": f"Svar: {question}"}


class AdminStub:
    def update_stock(self, ticker, **values):
        return {
            "ticker": ticker.upper(),
            **values,
            "backup_id": "20260809T120000Z-1234abcd",
        }

    def rollback(self, backup_id):
        return {"backup_id": backup_id, "restored": True}


def test_health_preserves_environment(monkeypatch):
    monkeypatch.setenv("STOCK_AGENT_ENV", "test")
    response = _get(create_app(_query()), "/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "environment": "test"}


def test_company_detail_contract():
    response = _get(
        create_app(_query(), PresentationStub()),
        "/api/stocks/nvda",
        params={"period": "1u"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ticker"] == "NVDA"
    assert body["company_name"] == "NVIDIA Corporation"
    assert body["recommendation"] == "KJØP / ØK"
    assert body["meta"]["model_version"] == "test-v1"
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


def test_phase_two_read_contracts_are_available():
    app = create_app(_query(), PresentationStub())

    for path in (
        "/api/today",
        "/api/explore",
        "/api/positions",
        "/api/watchlists",
        "/api/model-status",
        "/api/model-data",
        "/api/refresh/status",
    ):
        response = _get(app, path)
        assert response.status_code == 200, path

    search = _get(app, "/api/search", params={"q": "NVDA"})
    assert search.status_code == 200
    assert search.json()["query"] == "NVDA"


def test_chat_contract_and_input_validation():
    app = create_app(_query(), PresentationStub())

    response = _post(app, "/api/chat", {"question": "Oppsummer"})
    assert response.status_code == 200
    assert response.json()["answer"] == "Svar: Oppsummer"

    contextual = _post(app, "/api/chat", {
        "question": "Hva bør jeg følge med på?",
        "view": "detail",
        "ticker": "AAPL",
        "company_name": "Apple Inc.",
    })
    assert contextual.status_code == 200

    assert _post(app, "/api/chat", {"question": ""}).status_code == 422
    assert _get(app, "/api/search", params={"q": ""}).status_code == 422


def test_admin_contract_reads_and_writes_in_test(monkeypatch):
    monkeypatch.setenv("STOCK_AGENT_ENV", "test")
    app = create_app(_query(), PresentationStub(), AdminStub())

    state = _get(app, "/api/admin")
    assert state.status_code == 200
    assert state.json()["writable"] is True

    response = asyncio.run(_put(app, "/api/admin/stocks/nvda", {
        "owned": True,
        "average_cost": 125.5,
        "watchlists": ["USA"],
    }))
    assert response.status_code == 200
    assert response.json()["ticker"] == "NVDA"


def _put(app, path, json):
    async def request():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.put(path, json=json)
    return request()


def test_admin_requires_gav_when_owned(monkeypatch):
    monkeypatch.setenv("STOCK_AGENT_ENV", "test")
    app = create_app(_query(), PresentationStub(), AdminStub())
    response = asyncio.run(_put(app, "/api/admin/stocks/NVDA", {
        "owned": True,
        "average_cost": None,
        "watchlists": [],
    }))
    assert response.status_code == 422
