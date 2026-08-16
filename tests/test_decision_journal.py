from datetime import date, datetime, timezone
import json

import pandas as pd

from src.decision_journal import (
    build_decision_journal_entries,
    load_decision_journal,
    save_decision_journal,
    decision_journal_dir,
)
from src.recommendation_contract import build_contract_fields


def _context(actions=None):
    actions = actions if actions is not None else [
        {
            "ticker": "KMAR",
            "source": "opportunity_advisor",
            "rule": "candidate",
            "priority": 2,
            "dedupe_key": "candidate:KMAR",
            "reason": "Sterk kandidat.",
            "category": "Kjøpsmuligheter",
            "decision": build_contract_fields(
                ticker="KMAR.OL",
                category="Kjøpsmuligheter",
                rule="candidate",
                reason="Sterk kandidat.",
                confidence="høy",
            ),
        }
    ]
    return {
        "model_version": "test-model",
        "recommendations": {
            "model_version": "test-model",
            "actions": actions,
        },
    }


def test_builds_traceable_entry_from_structured_recommendation():
    entries = build_decision_journal_entries(
        _context(),
        signal_date=date(2026, 8, 10),
        recorded_at=datetime(2026, 8, 10, 6, 0, tzinfo=timezone.utc),
    )

    assert len(entries) == 1
    entry = entries[0]
    assert entry["signal_date"] == "2026-08-10"
    assert entry["recorded_at"] == "2026-08-10T06:00:00+00:00"
    assert entry["model_version"] == "test-model"
    assert entry["decision"]["ticker"] == "KMAR.OL"
    assert entry["decision"]["action_code"] == "consider_buy"
    assert entry["decision"]["target_price"] is None
    assert entry["evidence"]["reason"] == "Sterk kandidat."
    assert entry["evidence"]["region"] == "norway"
    assert entry["evidence"]["primary_profile"] == "unknown"
    assert entry["evidence"]["local_benchmark"] == "OSEBX.OL"


def test_captures_region_and_profile_from_signal_time_context():
    context = _context()
    context["discovery_candidates"] = pd.DataFrame(
        [
            {
                "ticker": "KMAR.OL",
                "primary_profile": "quality",
                "source_universe": "OBX",
                "technical_score": 82,
                "trend_regime": "STERK OPPTREND",
                "relative_strength_20d": 4.2,
            }
        ]
    )

    entry = build_decision_journal_entries(context)[0]

    assert entry["evidence"]["region"] == "norway"
    assert entry["evidence"]["primary_profile"] == "quality"
    assert entry["evidence"]["local_benchmark"] == "OSEBX.OL"
    reference = entry["evidence"]["technical_reference"]
    assert reference["version"] == "trend_momentum_v1"
    assert reference["status"] == "complete"
    assert reference["action"] == "buy"
    assert reference["inputs"]["relative_strength_20d"] == 4.2


def test_marks_technical_reference_unavailable_without_signal_time_inputs():
    entry = build_decision_journal_entries(_context())[0]

    reference = entry["evidence"]["technical_reference"]
    assert reference["status"] == "unavailable"
    assert "mangler" in reference["reason"].lower()


def test_deduplicates_same_material_advice():
    action = _context()["recommendations"]["actions"][0]

    entries = build_decision_journal_entries(_context([action, dict(action)]))

    assert len(entries) == 1


def test_uses_final_decisions_and_skips_non_material_status():
    material = _context()["recommendations"]["actions"][0]
    material = {
        **material,
        "dedupe_key": "FINAL_DECISION:KMAR.OL",
        "decision": {
            **material["decision"],
            "label": "Vurder kjøp",
            "material": True,
        },
    }
    non_material = {
        **material,
        "ticker": "DNB.OL",
        "dedupe_key": "FINAL_DECISION:DNB.OL",
        "decision": {
            **material["decision"],
            "ticker": "DNB.OL",
            "action_code": "hold",
            "label": "HOLD",
            "material": False,
        },
    }
    context = _context()
    context["recommendations"]["decisions"] = [material, non_material]

    entries = build_decision_journal_entries(context)

    assert len(entries) == 1
    assert entries[0]["decision"]["label"] == "Vurder kjøp"


def test_save_and_load_are_repeatable_for_same_day(tmp_path):
    path = tmp_path / "decisions.json"
    first = save_decision_journal(
        _context(),
        signal_date=date(2026, 8, 10),
        recorded_at=datetime(2026, 8, 10, 6, 0, tzinfo=timezone.utc),
        path=path,
    )
    second = save_decision_journal(
        _context(),
        signal_date=date(2026, 8, 10),
        recorded_at=datetime(2026, 8, 10, 7, 0, tzinfo=timezone.utc),
        path=path,
    )

    assert first == second == path
    entries = load_decision_journal(path)
    assert len(entries) == 1
    assert entries[0]["recorded_at"] == "2026-08-10T07:00:00+00:00"


def test_empty_and_invalid_journals_are_safe(tmp_path):
    assert save_decision_journal(_context([]), path=tmp_path / "empty.json") is None
    invalid = tmp_path / "decisions_invalid.json"
    invalid.write_text(json.dumps({"version": 999, "entries": [{}]}), encoding="utf-8")

    assert load_decision_journal(tmp_path) == []


def test_journal_directory_is_environment_separated(monkeypatch):
    monkeypatch.setenv("STOCK_AGENT_ENV", "test")
    assert decision_journal_dir().parts[-2:] == ("decision_journal", "test")
