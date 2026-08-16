from __future__ import annotations

from datetime import date, datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from src.benchmarks import local_benchmark_for_symbol
from src.model_version import MODEL_VERSION
from src.environment import get_environment
from src.recommendation_contract import StructuredRecommendation
from src.storage import atomic_write_json
from src.strategy_profiles import build_strategy_profile
from src.config import load_backtest_validation_config
from src.technical_baseline import (
    build_trend_momentum_reference_snapshot,
    region_for_symbol,
)


DECISION_JOURNAL_VERSION = 1


class DecisionJournalEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entry_id: str
    signal_date: str
    recorded_at: str
    model_version: str
    source: str
    rule: str | None = None
    priority: int | None = None
    dedupe_key: str
    decision: StructuredRecommendation
    evidence: dict[str, Any] = Field(default_factory=dict)


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def decision_journal_dir() -> Path:
    return _project_root() / "snapshots" / "decision_journal" / get_environment()


def decision_journal_path(signal_date: date | None = None) -> Path:
    signal_date = signal_date or date.today()
    return decision_journal_dir() / f"decisions_{signal_date.isoformat()}.json"


def _recorded_at(value: datetime | None) -> datetime:
    value = value or datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _entry_id(signal_date: date, model_version: str, dedupe_key: str) -> str:
    identity = f"{signal_date.isoformat()}:{model_version}:{dedupe_key}"
    return sha256(identity.encode("utf-8")).hexdigest()[:20]


def _text(value: Any) -> str | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    return text or None


def _metadata_rows(context: dict[str, Any]) -> dict[str, Any]:
    rows: dict[str, Any] = {}
    for key in ("portfolio_report", "watchlist_report", "discovery_candidates"):
        frame = context.get(key)
        if not isinstance(frame, pd.DataFrame) or frame.empty or "ticker" not in frame:
            continue
        for _, row in frame.iterrows():
            ticker = str(row.get("ticker") or "").strip().upper()
            if ticker:
                rows[ticker] = row
    return rows


def _opportunity_profiles(context: dict[str, Any]) -> dict[str, str]:
    profiles = {}
    for item in (context.get("opportunity_advisor") or {}).get("items") or []:
        ticker = str(item.get("ticker") or "").strip().upper()
        profile = _text(item.get("primary_profile"))
        if ticker and profile:
            profiles[ticker] = profile
    return profiles


def _journal_metadata(
    ticker: str,
    rows: dict[str, Any],
    opportunity_profiles: dict[str, str],
    *,
    validation_config: dict[str, Any],
) -> dict[str, Any]:
    profile = opportunity_profiles.get(ticker)
    row = rows.get(ticker)
    if profile is None and row is not None:
        profile = _text(row.get("primary_profile"))
        if profile is None:
            try:
                profile = _text(build_strategy_profile(row).get("primary_profile"))
            except Exception:
                profile = None
    return {
        "region": region_for_symbol(ticker),
        "primary_profile": profile or "unknown",
        "local_benchmark": local_benchmark_for_symbol(ticker),
        "technical_reference": build_trend_momentum_reference_snapshot(
            row,
            config=validation_config,
        ),
    }


def build_decision_journal_entries(
    context: dict[str, Any],
    *,
    signal_date: date | None = None,
    recorded_at: datetime | None = None,
) -> list[dict[str, Any]]:
    signal_date = signal_date or date.today()
    timestamp = _recorded_at(recorded_at).isoformat()
    recommendations = context.get("recommendations") or {}
    model_version = str(
        recommendations.get("model_version")
        or context.get("model_version")
        or MODEL_VERSION
    )

    entries = []
    seen = set()
    metadata_rows = _metadata_rows(context)
    opportunity_profiles = _opportunity_profiles(context)
    validation_config = load_backtest_validation_config()
    items = recommendations.get("decisions") or recommendations.get("actions") or []
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("decision"), dict):
            continue
        decision = StructuredRecommendation.model_validate(item["decision"])
        if not decision.material and recommendations.get("decisions"):
            continue
        dedupe_key = str(
            item.get("dedupe_key")
            or f"{decision.scope}:{decision.ticker}:{decision.action_code}"
        )
        identity = (model_version, dedupe_key)
        if identity in seen:
            continue
        seen.add(identity)
        evidence = {
            "reason": item.get("reason"),
            "category": item.get("category"),
            "briefing_section": item.get("briefing_section"),
            **_journal_metadata(
                str(decision.ticker).strip().upper(),
                metadata_rows,
                opportunity_profiles,
                validation_config=validation_config,
            ),
        }
        entry = DecisionJournalEntry(
            entry_id=_entry_id(signal_date, model_version, dedupe_key),
            signal_date=signal_date.isoformat(),
            recorded_at=timestamp,
            model_version=model_version,
            source=str(item.get("source") or "recommendation_engine"),
            rule=item.get("rule"),
            priority=item.get("priority"),
            dedupe_key=dedupe_key,
            decision=decision,
            evidence={key: value for key, value in evidence.items() if value is not None},
        )
        entries.append(entry.model_dump())

    return entries


def save_decision_journal(
    context: dict[str, Any],
    *,
    signal_date: date | None = None,
    recorded_at: datetime | None = None,
    path: Path | None = None,
) -> Path | None:
    signal_date = signal_date or date.today()
    entries = build_decision_journal_entries(
        context,
        signal_date=signal_date,
        recorded_at=recorded_at,
    )
    if not entries:
        return None

    destination = path or decision_journal_path(signal_date)
    payload = {
        "version": DECISION_JOURNAL_VERSION,
        "signal_date": signal_date.isoformat(),
        "entries": entries,
    }
    return atomic_write_json(destination, payload)


def load_decision_journal(path: Path | None = None) -> list[dict[str, Any]]:
    source = path or decision_journal_dir()
    if not source.exists():
        return []

    files = [source] if source.is_file() else sorted(source.glob("decisions_*.json"))
    entries = {}
    for file in files:
        try:
            payload = json.loads(file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if payload.get("version") != DECISION_JOURNAL_VERSION:
            continue
        for raw in payload.get("entries") or []:
            try:
                entry = DecisionJournalEntry.model_validate(raw).model_dump()
            except (TypeError, ValueError):
                continue
            entries[entry["entry_id"]] = entry

    return sorted(
        entries.values(),
        key=lambda item: (item["signal_date"], item["recorded_at"], item["entry_id"]),
    )
