#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import load_watchlists
from src.context import reload_context_from_snapshot
from src.migration_parity import build_migration_parity_report
from src.presentation_queries import PresentationQueries
from src.storage import load_portfolio


def main() -> int:
    environment = os.getenv("STOCK_AGENT_ENV", "test").strip().lower()
    allow_prod = "--allow-prod-read-only" in sys.argv[1:]
    if environment not in {"test", "prod"}:
        print(f"Avbrutt: ukjent miljø {environment!r}.")
        return 2
    if environment == "prod" and not allow_prod:
        print(
            "Avbrutt: PROD krever eksplisitt --allow-prod-read-only. "
            "Verifikatoren gjør ingen skriveoperasjoner."
        )
        return 2

    loaded = reload_context_from_snapshot()
    context = loaded.get("context") if loaded.get("loaded") else None
    if not isinstance(context, dict):
        print("Avbrutt: TEST-snapshot mangler eller er ugyldig. Kjør Daily Refresh.")
        return 2

    report = build_migration_parity_report(
        PresentationQueries(),
        context,
        load_portfolio([]),
        load_watchlists(),
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
