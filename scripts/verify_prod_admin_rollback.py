#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.admin_service import AdminMutationService
from src.storage import data_path


def _read_optional(path: Path):
    if not path.exists():
        return {"exists": False, "value": None}
    with open(path, "r", encoding="utf-8") as stream:
        return {"exists": True, "value": json.load(stream)}


def _position_cost(position: dict) -> float | None:
    value = position.get("buy_price", position.get("average_cost"))
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Kontrollert, semantisk uendret PROD-skriving med rollback."
    )
    parser.add_argument("--ticker", default="SUBC.OL")
    parser.add_argument("--confirm-prod-write-rollback", action="store_true")
    args = parser.parse_args()

    if os.getenv("STOCK_AGENT_ENV", "test").strip().lower() != "prod":
        print("Avbrutt: STOCK_AGENT_ENV må være prod.")
        return 2
    if os.getenv("STOCK_AGENT_ENABLE_PROD_WRITES") != "1":
        print("Avbrutt: STOCK_AGENT_ENABLE_PROD_WRITES=1 mangler.")
        return 2
    if not args.confirm_prod_write_rollback:
        print("Avbrutt: eksplisitt --confirm-prod-write-rollback mangler.")
        return 2

    ticker = args.ticker.strip().upper()
    paths = {
        name: data_path(name)
        for name in ("portfolio.json", "watchlists.json", "writer_owner.json")
    }
    original = {name: _read_optional(path) for name, path in paths.items()}
    portfolio = original["portfolio.json"]["value"] or []
    watchlists = original["watchlists.json"]["value"] or {}
    matches = [
        position
        for position in portfolio
        if str(position.get("ticker", "")).upper() == ticker
    ]
    if len(matches) != 1:
        print(f"Avbrutt: {ticker} må finnes nøyaktig én gang i PROD-porteføljen.")
        return 2
    average_cost = _position_cost(matches[0])
    if average_cost is None or average_cost <= 0:
        print(f"Avbrutt: {ticker} mangler gyldig GAV.")
        return 2
    memberships = sorted(
        name
        for name, symbols in watchlists.items()
        if ticker in {str(symbol).upper() for symbol in symbols}
    )

    service = AdminMutationService()
    backup_id = None
    error = None
    try:
        result = service.update_stock(
            ticker,
            owned=True,
            average_cost=average_cost,
            watchlists=memberships,
        )
        backup_id = result["backup_id"]
        service.rollback(backup_id)
    except Exception as exc:  # recovery is more important than exception type here
        error = f"{type(exc).__name__}: {exc}"
        if backup_id:
            try:
                service.rollback(backup_id)
            except Exception as recovery_exc:
                error += f"; rollback feilet: {type(recovery_exc).__name__}: {recovery_exc}"

    restored = {name: _read_optional(path) for name, path in paths.items()}
    checks = {
        "portfolio_restored": restored["portfolio.json"] == original["portfolio.json"],
        "watchlists_restored": restored["watchlists.json"] == original["watchlists.json"],
        "writer_owner_restored": restored["writer_owner.json"] == original["writer_owner.json"],
        "backup_exists": bool(
            backup_id and (data_path("backups") / f"{backup_id}.json").exists()
        ),
    }
    passed = error is None and all(checks.values())
    report = {
        "status": "PASS" if passed else "FAIL",
        "ticker": ticker,
        "average_cost": average_cost,
        "watchlists": memberships,
        "backup_id": backup_id,
        "checks": checks,
        "error": error,
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
