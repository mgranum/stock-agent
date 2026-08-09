#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import sys

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.api.app import create_app
from src.presentation_queries import PresentationQueries


async def main() -> int:
    environment = os.getenv("STOCK_AGENT_ENV", "test").strip().lower()
    if environment != "test":
        print("Avbrutt: driftsverifikasjonen skal kjøres med STOCK_AGENT_ENV=test.")
        return 2

    first = PresentationQueries()
    first_today = first.today()
    owned = first_today.get("owned") or []
    watchlist = first_today.get("watchlist") or []
    representative = (owned or watchlist)[0]["ticker"] if owned or watchlist else None
    if not representative:
        print("Avbrutt: TEST-snapshotet har ingen representativ ticker.")
        return 2

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        responses = {
            "health": await client.get("/api/health"),
            "today": await client.get("/api/today"),
            "explore": await client.get("/api/explore"),
            "model_data": await client.get("/api/model-data"),
            "company": await client.get(
                f"/api/stocks/{representative}", params={"period": "3m"}
            ),
            "direct_route": await client.get(
                f"/stocks/{representative}", params={"period": "3m"}
            ),
        }

    checks = []
    for name, response in responses.items():
        checks.append(
            {
                "name": f"HTTP {name}",
                "passed": response.status_code == 200,
                "detail": f"status={response.status_code}",
            }
        )

    company_payload = responses["company"].json() if responses["company"].status_code == 200 else {}
    checks.append(
        {
            "name": "kurscache 3m",
            "passed": bool(company_payload.get("candles")),
            "detail": f"ticker={representative}, datapunkter={len(company_payload.get('candles') or [])}",
        }
    )

    second_today = PresentationQueries().today()
    stable_fields = ("ticker", "recommendation", "score", "average_cost", "stop_level")
    first_rows = [
        {key: row.get(key) for key in stable_fields}
        for row in first_today.get("owned", []) + first_today.get("watchlist", [])
    ]
    second_rows = [
        {key: row.get(key) for key in stable_fields}
        for row in second_today.get("owned", []) + second_today.get("watchlist", [])
    ]
    checks.append(
        {
            "name": "gjenoppretting etter ny query-instans",
            "passed": first_rows == second_rows,
            "detail": f"rader={len(first_rows)}",
        }
    )

    refresh = first.refresh_status()
    checks.append(
        {
            "name": "refresh-status kan leses",
            "passed": bool(refresh.get("status")) and refresh.get("environment") == "test",
            "detail": f"status={refresh.get('status')}, miljø={refresh.get('environment')}",
        }
    )

    failed = [check for check in checks if not check["passed"]]
    report = {
        "status": "PASS" if not failed else "FAIL",
        "passed": len(checks) - len(failed),
        "failed": len(failed),
        "checks": checks,
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
