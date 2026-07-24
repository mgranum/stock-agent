from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def universe_snapshot_path(snapshot_date: date | None = None) -> Path:
    snapshot_date = snapshot_date or date.today()
    return (
        _project_root()
        / "snapshots"
        / "universes"
        / f"screening_universe_{snapshot_date.isoformat()}.json"
    )


def normalize_universes(universes) -> dict[str, list[str]]:
    if not isinstance(universes, dict):
        return {}

    normalized = {}
    for name, symbols in universes.items():
        if not isinstance(symbols, list):
            continue
        clean_symbols = []
        seen = set()
        for symbol in symbols:
            ticker = str(symbol or "").strip().upper()
            if not ticker or ticker in seen:
                continue
            seen.add(ticker)
            clean_symbols.append(ticker)
        normalized[str(name)] = clean_symbols
    return normalized


def save_universe_snapshot(
    universes,
    snapshot_date: date | None = None,
) -> Path:
    snapshot_date = snapshot_date or date.today()
    path = universe_snapshot_path(snapshot_date)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "snapshot_version": 1,
        "snapshot_date": snapshot_date.isoformat(),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "data/config/screening_universe.json",
        "universes": normalize_universes(universes),
    }
    with open(path, "w", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, ensure_ascii=False)
    return path
