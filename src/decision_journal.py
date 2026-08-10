from __future__ import annotations

from datetime import date, datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.model_version import MODEL_VERSION
from src.recommendation_contract import StructuredRecommendation
from src.storage import atomic_write_json


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
    return _project_root() / "snapshots" / "decision_journal"


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
