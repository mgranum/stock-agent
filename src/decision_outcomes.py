from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from src.data import get_daily_prices
from src.decision_journal import load_decision_journal
from src.environment import get_environment
from src.storage import atomic_write_json
from src.technical_baseline import _adjust_ohlc_prices


DECISION_OUTCOME_VERSION = 1
DECISION_HORIZONS = (5, 10, 20, 40)


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def decision_outcome_path() -> Path:
    return (
        _project_root()
        / "snapshots"
        / "decision_journal_outcomes"
        / get_environment()
        / "outcomes.json"
    )


def _finite(value) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if pd.notna(number) else None


def _pct(value: float, entry: float) -> float:
    return round((value / entry - 1) * 100, 4)


def _level_event(raw_future: pd.DataFrame, target: float | None, stop: float | None):
    for timestamp, row in raw_future.iloc[: max(DECISION_HORIZONS)].iterrows():
        high = _finite(row.get("high", row.get("close")))
        low = _finite(row.get("low", row.get("close")))
        target_hit = target is not None and high is not None and high >= target
        stop_hit = stop is not None and low is not None and low <= stop
        if target_hit or stop_hit:
            return {
                "event": (
                    "both_same_day"
                    if target_hit and stop_hit
                    else "target"
                    if target_hit
                    else "stop"
                ),
                "date": timestamp.date().isoformat(),
            }
    return None


def _evaluate_entry(entry: dict[str, Any], prices: pd.DataFrame) -> dict[str, Any]:
    signal_date = pd.Timestamp(entry["signal_date"])
    if prices is None or prices.empty:
        raise ValueError("Prisdata mangler")

    raw = prices.copy().sort_index()
    adjusted = _adjust_ohlc_prices(raw)
    raw_future = raw[raw.index > signal_date]
    adjusted_future = adjusted[adjusted.index > signal_date]
    if raw_future.empty or adjusted_future.empty:
        return {
            "status": "pending",
            "message": "Ingen handelsdag etter signalet ennå.",
            "horizons": {},
            "first_level_hit": None,
        }

    entry_price = _finite(adjusted_future.iloc[0].get("open"))
    if entry_price is None or entry_price <= 0:
        entry_price = _finite(adjusted_future.iloc[0].get("close"))
    if entry_price is None or entry_price <= 0:
        raise ValueError("Gyldig inngangspris mangler")

    decision = entry["decision"]
    target = _finite(decision.get("target_price"))
    stop = _finite(decision.get("stop_level"))
    horizons = {}
    completed = 0
    for horizon in DECISION_HORIZONS:
        if len(adjusted_future) < horizon:
            horizons[str(horizon)] = {"status": "pending"}
            continue
        path = adjusted_future.iloc[:horizon]
        exit_price = _finite(path.iloc[-1].get("close"))
        highs = pd.to_numeric(path.get("high"), errors="coerce").dropna()
        lows = pd.to_numeric(path.get("low"), errors="coerce").dropna()
        if exit_price is None or highs.empty or lows.empty:
            horizons[str(horizon)] = {
                "status": "insufficient",
                "message": "Prisbanen mangler close, high eller low.",
            }
            continue
        completed += 1
        horizons[str(horizon)] = {
            "status": "complete",
            "exit_date": path.index[-1].date().isoformat(),
            "return_pct": _pct(exit_price, entry_price),
            "max_favorable_pct": _pct(float(highs.max()), entry_price),
            "max_adverse_pct": _pct(float(lows.min()), entry_price),
        }

    status = (
        "complete"
        if completed == len(DECISION_HORIZONS)
        else "partial"
        if completed > 0
        else "pending"
    )
    return {
        "status": status,
        "entry_date": adjusted_future.index[0].date().isoformat(),
        "entry_price": round(entry_price, 4),
        "horizons": horizons,
        "first_level_hit": _level_event(raw_future, target, stop),
    }


def evaluate_decision_journal(
    entries: list[dict[str, Any]] | None = None,
    *,
    price_loader: Callable[[str], pd.DataFrame] | None = None,
    evaluated_at: datetime | None = None,
) -> list[dict[str, Any]]:
    entries = load_decision_journal() if entries is None else entries
    loader = price_loader or (
        lambda ticker: get_daily_prices(ticker, period="1y", use_cache=True)
    )
    evaluated_at = evaluated_at or datetime.now(timezone.utc)
    if evaluated_at.tzinfo is None:
        evaluated_at = evaluated_at.replace(tzinfo=timezone.utc)
    timestamp = evaluated_at.astimezone(timezone.utc).isoformat()
    cache = {}
    outcomes = []

    for entry in entries:
        decision = entry.get("decision") or {}
        ticker = str(decision.get("ticker") or "").strip().upper()
        outcome = {
            "entry_id": entry.get("entry_id"),
            "signal_date": entry.get("signal_date"),
            "ticker": ticker,
            "action_code": decision.get("action_code"),
            "evaluated_at": timestamp,
        }
        try:
            if ticker not in cache:
                cache[ticker] = loader(ticker)
            outcome.update(_evaluate_entry(entry, cache[ticker]))
        except Exception as exc:
            outcome.update(
                {
                    "status": "error",
                    "message": str(exc) or exc.__class__.__name__,
                    "horizons": {},
                    "first_level_hit": None,
                }
            )
        outcomes.append(outcome)

    return outcomes


def save_decision_outcomes(
    outcomes: list[dict[str, Any]],
    path: Path | None = None,
) -> Path | None:
    if not outcomes:
        return None
    destination = path or decision_outcome_path()
    return atomic_write_json(
        destination,
        {"version": DECISION_OUTCOME_VERSION, "outcomes": outcomes},
    )


def load_decision_outcomes(path: Path | None = None) -> list[dict[str, Any]]:
    source = path or decision_outcome_path()
    if not source.exists():
        return []
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if payload.get("version") != DECISION_OUTCOME_VERSION:
        return []
    return [item for item in payload.get("outcomes") or [] if isinstance(item, dict)]
