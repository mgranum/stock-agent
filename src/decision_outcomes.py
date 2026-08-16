from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from math import ceil
from statistics import median
from typing import Any, Callable

import pandas as pd

from src.benchmarks import (
    GLOBAL_EQUITY_BENCHMARK,
    local_benchmark_for_symbol,
    local_benchmark_label,
)
from src.config import load_backtest_validation_config
from src.data import get_daily_prices
from src.decision_journal import load_decision_journal
from src.discovery_validation import _net_returns
from src.environment import get_environment
from src.storage import atomic_write_json
from src.technical_baseline import (
    TECHNICAL_REFERENCE_VERSION,
    _adjust_ohlc_prices,
)


DECISION_OUTCOME_VERSION = 1
DECISION_HORIZONS = (5, 10, 20, 40)
MIN_MATURE_OUTCOMES_PER_HORIZON = 30
MIN_COMPLETE_40D_OUTCOMES = 60
BENCHMARK_ELIGIBLE_ACTIONS = frozenset({"consider_buy"})
BENCHMARK_DECISION_GATE_VERSION = "2026.08.15-v2"
BENCHMARK_GATE_HORIZONS = (10, 20, 40)
BENCHMARK_GATE_WIN_HORIZONS = (20, 40)
MIN_SEGMENT_OBSERVATIONS = 10
MIN_METADATA_COVERAGE_PCT = 90.0
MAX_SEGMENT_SHARE_PCT = 80.0
TOP_WINNER_TRIM_PCT = 5.0


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


def _evaluate_benchmark(signal_date: str, prices: pd.DataFrame) -> dict[str, Any]:
    if prices is None or prices.empty:
        raise ValueError("Benchmarkdata mangler")

    adjusted = _adjust_ohlc_prices(prices.copy().sort_index())
    future = adjusted[adjusted.index > pd.Timestamp(signal_date)]
    if future.empty:
        return {
            "status": "pending",
            "message": "Ingen benchmark-handelsdag etter signalet ennå.",
            "horizons": {},
        }

    entry_price = _finite(future.iloc[0].get("open"))
    if entry_price is None or entry_price <= 0:
        entry_price = _finite(future.iloc[0].get("close"))
    if entry_price is None or entry_price <= 0:
        raise ValueError("Gyldig benchmark-inngangspris mangler")

    horizons = {}
    completed = 0
    for horizon in DECISION_HORIZONS:
        if len(future) < horizon:
            horizons[str(horizon)] = {"status": "pending"}
            continue
        exit_row = future.iloc[horizon - 1]
        exit_price = _finite(exit_row.get("close"))
        if exit_price is None:
            horizons[str(horizon)] = {
                "status": "insufficient",
                "message": "Benchmarkbanen mangler close.",
            }
            continue
        completed += 1
        horizons[str(horizon)] = {
            "status": "complete",
            "exit_date": exit_row.name.date().isoformat(),
            "return_pct": _pct(exit_price, entry_price),
        }

    return {
        "status": (
            "complete"
            if completed == len(DECISION_HORIZONS)
            else "partial"
            if completed > 0
            else "pending"
        ),
        "entry_date": future.index[0].date().isoformat(),
        "entry_price": round(entry_price, 4),
        "horizons": horizons,
    }


def _attach_benchmark(
    outcome: dict[str, Any],
    benchmark_result: dict[str, Any],
) -> None:
    outcome["benchmark"] = {
        key: value
        for key, value in {
            "symbol": GLOBAL_EQUITY_BENCHMARK,
            "status": benchmark_result.get("status"),
            "message": benchmark_result.get("message"),
            "entry_date": benchmark_result.get("entry_date"),
            "entry_price": benchmark_result.get("entry_price"),
        }.items()
        if value is not None
    }
    benchmark_horizons = benchmark_result.get("horizons") or {}
    for horizon, result in (outcome.get("horizons") or {}).items():
        if not isinstance(result, dict) or result.get("status") != "complete":
            continue
        benchmark = benchmark_horizons.get(horizon) or {}
        benchmark_status = str(
            benchmark.get("status")
            or benchmark_result.get("status")
            or "pending"
        )
        result["benchmark_status"] = benchmark_status
        if benchmark_status != "complete":
            continue
        benchmark_return = _finite(benchmark.get("return_pct"))
        stock_return = _finite(result.get("return_pct"))
        if benchmark_return is None or stock_return is None:
            result["benchmark_status"] = "insufficient"
            continue
        result["benchmark_return_pct"] = round(benchmark_return, 4)
        result["relative_return_pct"] = round(
            stock_return - benchmark_return,
            4,
        )


def _cost_model(config: dict[str, Any]) -> dict[str, Any]:
    capital = _finite((config.get("execution") or {}).get("initial_cash"))
    costs = config.get("costs")
    if capital is None or capital <= 0:
        raise ValueError("Kostnadsmodellen krever positiv startkapital")
    if not isinstance(costs, dict):
        raise ValueError("Kostnadsmodellen mangler kostnadsforutsetninger")
    assumptions = {
        "initial_capital": capital,
        "costs": costs,
    }
    encoded = json.dumps(
        assumptions,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        **assumptions,
        "fingerprint": sha256(encoded).hexdigest()[:16],
    }


def _attach_net_benchmark(
    outcome: dict[str, Any],
    stock_net: dict[int, dict[str, Any]],
    benchmark_net: dict[int, dict[str, Any]],
    cost_model: dict[str, Any],
) -> None:
    outcome["cost_evaluation"] = {
        "status": "complete",
        **cost_model,
    }
    for horizon, result in (outcome.get("horizons") or {}).items():
        if not isinstance(result, dict) or result.get("benchmark_status") != "complete":
            continue
        stock = stock_net.get(int(horizon))
        benchmark = benchmark_net.get(int(horizon))
        if not stock or not benchmark:
            result["cost_status"] = "insufficient"
            continue
        stock_return = _finite(stock.get("return_pct"))
        benchmark_return = _finite(benchmark.get("return_pct"))
        if stock_return is None or benchmark_return is None:
            result["cost_status"] = "insufficient"
            continue
        result["cost_status"] = "complete"
        result["net_return_pct"] = round(stock_return, 4)
        result["benchmark_net_return_pct"] = round(benchmark_return, 4)
        result["net_relative_return_pct"] = round(
            stock_return - benchmark_return,
            4,
        )


def _attach_local_benchmark(
    outcome: dict[str, Any],
    symbol: str,
    benchmark_result: dict[str, Any],
) -> None:
    outcome["local_benchmark"] = {
        key: value
        for key, value in {
            "symbol": symbol,
            "label": local_benchmark_label(symbol),
            "status": benchmark_result.get("status"),
            "message": benchmark_result.get("message"),
            "entry_date": benchmark_result.get("entry_date"),
            "entry_price": benchmark_result.get("entry_price"),
        }.items()
        if value is not None
    }
    benchmark_horizons = benchmark_result.get("horizons") or {}
    for horizon, result in (outcome.get("horizons") or {}).items():
        if not isinstance(result, dict) or result.get("status") != "complete":
            continue
        benchmark = benchmark_horizons.get(horizon) or {}
        benchmark_status = str(
            benchmark.get("status")
            or benchmark_result.get("status")
            or "pending"
        )
        result["local_benchmark_status"] = benchmark_status
        if benchmark_status != "complete":
            continue
        benchmark_return = _finite(benchmark.get("return_pct"))
        stock_return = _finite(result.get("return_pct"))
        if benchmark_return is None or stock_return is None:
            result["local_benchmark_status"] = "insufficient"
            continue
        result["local_benchmark_return_pct"] = round(benchmark_return, 4)
        result["local_relative_return_pct"] = round(
            stock_return - benchmark_return,
            4,
        )


def _attach_local_net_benchmark(
    outcome: dict[str, Any],
    stock_net: dict[int, dict[str, Any]],
    benchmark_net: dict[int, dict[str, Any]],
    cost_model: dict[str, Any],
) -> None:
    outcome.setdefault(
        "cost_evaluation",
        {"status": "complete", **cost_model},
    )
    for horizon, result in (outcome.get("horizons") or {}).items():
        if (
            not isinstance(result, dict)
            or result.get("local_benchmark_status") != "complete"
        ):
            continue
        stock = stock_net.get(int(horizon))
        benchmark = benchmark_net.get(int(horizon))
        if not stock or not benchmark:
            result["local_cost_status"] = "insufficient"
            continue
        stock_return = _finite(stock.get("return_pct"))
        benchmark_return = _finite(benchmark.get("return_pct"))
        if stock_return is None or benchmark_return is None:
            result["local_cost_status"] = "insufficient"
            continue
        result["local_cost_status"] = "complete"
        result.setdefault("net_return_pct", round(stock_return, 4))
        result["local_benchmark_net_return_pct"] = round(benchmark_return, 4)
        result["local_net_relative_return_pct"] = round(
            stock_return - benchmark_return,
            4,
        )


def _attach_technical_reference(
    outcome: dict[str, Any],
    reference: dict[str, Any],
    stock_net: dict[int, dict[str, Any]],
    cost_model: dict[str, Any],
) -> None:
    outcome["technical_reference"] = dict(reference)
    action = str(reference.get("action") or "")
    if reference.get("status") != "complete" or action not in {"buy", "cash"}:
        outcome["technical_reference"]["evaluation_status"] = "unavailable"
        return

    outcome["technical_reference"]["evaluation_status"] = "complete"
    outcome.setdefault(
        "cost_evaluation",
        {"status": "complete", **cost_model},
    )
    for horizon, result in (outcome.get("horizons") or {}).items():
        if not isinstance(result, dict) or result.get("status") != "complete":
            continue
        stock = stock_net.get(int(horizon))
        stock_net_return = _finite((stock or {}).get("return_pct"))
        model_return = _finite(result.get("return_pct"))
        if stock_net_return is None or model_return is None:
            result["technical_reference_status"] = "insufficient"
            continue
        result["technical_reference_status"] = "complete"
        result.setdefault("net_return_pct", round(stock_net_return, 4))
        reference_return = model_return if action == "buy" else 0.0
        reference_net_return = stock_net_return if action == "buy" else 0.0
        result["technical_reference_return_pct"] = round(reference_return, 4)
        result["technical_reference_net_return_pct"] = round(
            reference_net_return,
            4,
        )
        result["model_vs_technical_return_pct"] = round(
            model_return - reference_return,
            4,
        )
        result["model_vs_technical_net_return_pct"] = round(
            stock_net_return - reference_net_return,
            4,
        )


def evaluate_decision_journal(
    entries: list[dict[str, Any]] | None = None,
    *,
    price_loader: Callable[[str], pd.DataFrame] | None = None,
    evaluated_at: datetime | None = None,
    validation_config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    entries = load_decision_journal() if entries is None else entries
    loader = price_loader or (
        lambda ticker: get_daily_prices(ticker, period="1y", use_cache=True)
    )
    evaluated_at = evaluated_at or datetime.now(timezone.utc)
    if evaluated_at.tzinfo is None:
        evaluated_at = evaluated_at.replace(tzinfo=timezone.utc)
    timestamp = evaluated_at.astimezone(timezone.utc).isoformat()
    cost_model = _cost_model(
        load_backtest_validation_config()
        if validation_config is None
        else validation_config
    )
    cache = {}
    net_cache = {}
    outcomes = []

    def prices_for(symbol: str) -> pd.DataFrame:
        if symbol not in cache:
            try:
                cache[symbol] = loader(symbol)
            except Exception as exc:
                cache[symbol] = exc
        value = cache[symbol]
        if isinstance(value, Exception):
            raise value
        return value

    def net_returns_for(
        symbol: str,
        signal_date: str,
        *,
        cost_symbol: str | None = None,
    ) -> dict[int, dict[str, Any]]:
        key = (symbol, signal_date, cost_symbol)
        if key not in net_cache:
            net_cache[key] = _net_returns(
                symbol,
                prices_for(symbol),
                signal_date,
                DECISION_HORIZONS,
                cost_model["initial_capital"],
                cost_model["costs"],
                cost_symbol=cost_symbol,
            )
        return net_cache[key]

    for entry in entries:
        decision = entry.get("decision") or {}
        evidence = entry.get("evidence") or {}
        ticker = str(decision.get("ticker") or "").strip().upper()
        outcome = {
            "entry_id": entry.get("entry_id"),
            "signal_date": entry.get("signal_date"),
            "ticker": ticker,
            "action_code": decision.get("action_code"),
            "scope": decision.get("scope"),
            "region": evidence.get("region"),
            "primary_profile": evidence.get("primary_profile"),
            "technical_reference": (
                dict(evidence.get("technical_reference"))
                if isinstance(evidence.get("technical_reference"), dict)
                else {
                    "version": TECHNICAL_REFERENCE_VERSION,
                    "status": "unavailable",
                    "reason": "Teknisk referanse ble ikke lagret på signaltidspunktet.",
                }
            ),
            "evaluated_at": timestamp,
        }
        try:
            outcome.update(_evaluate_entry(entry, prices_for(ticker)))
        except Exception as exc:
            outcome.update(
                {
                    "status": "error",
                    "message": str(exc) or exc.__class__.__name__,
                    "horizons": {},
                    "first_level_hit": None,
                }
            )
        if (
            outcome.get("status") != "error"
            and outcome.get("action_code") in BENCHMARK_ELIGIBLE_ACTIONS
        ):
            try:
                benchmark_result = _evaluate_benchmark(
                    str(entry.get("signal_date") or ""),
                    prices_for(GLOBAL_EQUITY_BENCHMARK),
                )
            except Exception as exc:
                benchmark_result = {
                    "status": "error",
                    "message": str(exc) or exc.__class__.__name__,
                    "horizons": {},
                }
            _attach_benchmark(outcome, benchmark_result)
            if benchmark_result.get("status") != "error":
                try:
                    signal_date = str(entry.get("signal_date") or "")
                    _attach_net_benchmark(
                        outcome,
                        net_returns_for(ticker, signal_date),
                        net_returns_for(GLOBAL_EQUITY_BENCHMARK, signal_date),
                        cost_model,
                    )
                except Exception as exc:
                    outcome["cost_evaluation"] = {
                        "status": "error",
                        "message": str(exc) or exc.__class__.__name__,
                        **cost_model,
                    }
                    for result in (outcome.get("horizons") or {}).values():
                        if isinstance(result, dict) and result.get("benchmark_status") == "complete":
                            result["cost_status"] = "error"
            local_symbol = str(
                evidence.get("local_benchmark")
                or local_benchmark_for_symbol(ticker)
            )
            try:
                local_result = _evaluate_benchmark(
                    str(entry.get("signal_date") or ""),
                    prices_for(local_symbol),
                )
            except Exception as exc:
                local_result = {
                    "status": "error",
                    "message": str(exc) or exc.__class__.__name__,
                    "horizons": {},
                }
            _attach_local_benchmark(outcome, local_symbol, local_result)
            if local_result.get("status") != "error":
                try:
                    signal_date = str(entry.get("signal_date") or "")
                    _attach_local_net_benchmark(
                        outcome,
                        net_returns_for(ticker, signal_date),
                        net_returns_for(
                            local_symbol,
                            signal_date,
                            cost_symbol=ticker,
                        ),
                        cost_model,
                    )
                except Exception as exc:
                    outcome["local_benchmark"]["cost_status"] = "error"
                    outcome["local_benchmark"]["cost_message"] = (
                        str(exc) or exc.__class__.__name__
                    )
                    for result in (outcome.get("horizons") or {}).values():
                        if (
                            isinstance(result, dict)
                            and result.get("local_benchmark_status") == "complete"
                        ):
                            result["local_cost_status"] = "error"
            reference = outcome["technical_reference"]
            if reference.get("status") == "complete":
                try:
                    _attach_technical_reference(
                        outcome,
                        reference,
                        net_returns_for(
                            ticker,
                            str(entry.get("signal_date") or ""),
                        ),
                        cost_model,
                    )
                except Exception as exc:
                    outcome["technical_reference"]["evaluation_status"] = "error"
                    outcome["technical_reference"]["evaluation_message"] = (
                        str(exc) or exc.__class__.__name__
                    )
                    for result in (outcome.get("horizons") or {}).values():
                        if isinstance(result, dict) and result.get("status") == "complete":
                            result["technical_reference_status"] = "error"
            else:
                outcome["technical_reference"]["evaluation_status"] = "unavailable"
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


def _horizon_statistics(observations: list[dict[str, Any]]) -> dict[str, float]:
    returns = [float(item["return_pct"]) for item in observations]
    favorable = [float(item["max_favorable_pct"]) for item in observations]
    adverse = [float(item["max_adverse_pct"]) for item in observations]
    return {
        "average_return_pct": round(sum(returns) / len(returns), 2),
        "median_return_pct": round(median(returns), 2),
        "positive_return_pct": round(
            sum(value > 0 for value in returns) / len(returns) * 100,
            1,
        ),
        "average_max_favorable_pct": round(sum(favorable) / len(favorable), 2),
        "average_max_adverse_pct": round(sum(adverse) / len(adverse), 2),
    }


def _benchmark_statistics(observations: list[dict[str, Any]]) -> dict[str, float]:
    stock_returns = [float(item["return_pct"]) for item in observations]
    benchmark_returns = [float(item["benchmark_return_pct"]) for item in observations]
    relative_returns = [float(item["relative_return_pct"]) for item in observations]
    net_returns = [float(item["net_return_pct"]) for item in observations]
    benchmark_net_returns = [
        float(item["benchmark_net_return_pct"]) for item in observations
    ]
    net_relative_returns = [
        float(item["net_relative_return_pct"]) for item in observations
    ]

    def trimmed(values):
        if len(values) == 1:
            return values
        trim_count = min(
            len(values) - 1,
            max(1, ceil(len(values) * TOP_WINNER_TRIM_PCT / 100)),
        )
        return sorted(values)[:-trim_count]

    trimmed_returns = trimmed(relative_returns)
    trimmed_net_returns = trimmed(net_relative_returns)
    return {
        "average_stock_return_pct": round(sum(stock_returns) / len(stock_returns), 2),
        "average_benchmark_return_pct": round(
            sum(benchmark_returns) / len(benchmark_returns),
            2,
        ),
        "average_relative_return_pct": round(
            sum(relative_returns) / len(relative_returns),
            2,
        ),
        "median_relative_return_pct": round(median(relative_returns), 2),
        "trimmed_average_relative_return_pct": round(
            sum(trimmed_returns) / len(trimmed_returns),
            2,
        ),
        "benchmark_win_pct": round(
            sum(value > 0 for value in relative_returns) / len(relative_returns) * 100,
            1,
        ),
        "average_net_return_pct": round(sum(net_returns) / len(net_returns), 2),
        "average_benchmark_net_return_pct": round(
            sum(benchmark_net_returns) / len(benchmark_net_returns),
            2,
        ),
        "average_net_relative_return_pct": round(
            sum(net_relative_returns) / len(net_relative_returns),
            2,
        ),
        "median_net_relative_return_pct": round(
            median(net_relative_returns),
            2,
        ),
        "trimmed_average_net_relative_return_pct": round(
            sum(trimmed_net_returns) / len(trimmed_net_returns),
            2,
        ),
        "net_benchmark_win_pct": round(
            sum(value > 0 for value in net_relative_returns)
            / len(net_relative_returns)
            * 100,
            1,
        ),
    }


def _segment_report(
    observations: list[dict[str, Any]],
    field: str,
) -> dict[str, Any]:
    known = [
        item
        for item in observations
        if str(item.get(field) or "").strip().lower() not in {"", "unknown"}
    ]
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in known:
        key = str(item[field]).strip().lower()
        grouped.setdefault(key, []).append(item)

    segments = []
    for key, items in sorted(grouped.items()):
        complete = len(items)
        sufficient = complete >= MIN_SEGMENT_OBSERVATIONS
        statistics = _benchmark_statistics(items) if sufficient else None
        segments.append(
            {
                "key": key,
                "complete": complete,
                "share_pct": (
                    round(complete / len(observations) * 100, 1)
                    if observations
                    else 0.0
                ),
                "minimum_required": MIN_SEGMENT_OBSERVATIONS,
                "sufficient": sufficient,
                "statistics": statistics,
            }
        )

    largest_share = max(
        (item["share_pct"] for item in segments),
        default=0.0,
    )
    positive_segments = sum(
        item["sufficient"]
        and item["statistics"]["average_net_relative_return_pct"] > 0
        for item in segments
    )
    return {
        "metadata_coverage_pct": (
            round(len(known) / len(observations) * 100, 1)
            if observations
            else 0.0
        ),
        "largest_share_pct": largest_share,
        "positive_segments": positive_segments,
        "minimum_segment_observations": MIN_SEGMENT_OBSERVATIONS,
        "segments": segments,
    }


def _local_observation(result: dict[str, Any]) -> dict[str, Any] | None:
    required = {
        "return_pct": "return_pct",
        "benchmark_return_pct": "local_benchmark_return_pct",
        "relative_return_pct": "local_relative_return_pct",
        "net_return_pct": "net_return_pct",
        "benchmark_net_return_pct": "local_benchmark_net_return_pct",
        "net_relative_return_pct": "local_net_relative_return_pct",
    }
    if (
        result.get("local_benchmark_status") != "complete"
        or result.get("local_cost_status") != "complete"
        or any(_finite(result.get(source)) is None for source in required.values())
    ):
        return None
    return {
        target: float(result[source])
        for target, source in required.items()
    }


def _build_local_benchmark_report(
    outcomes: list[dict[str, Any]],
    *,
    min_mature_per_horizon: int,
) -> dict[str, Any]:
    eligible = [
        outcome
        for outcome in outcomes
        if outcome.get("action_code") in BENCHMARK_ELIGIBLE_ACTIONS
    ]
    grouped: dict[str, list[dict[str, Any]]] = {}
    for outcome in eligible:
        symbol = str((outcome.get("local_benchmark") or {}).get("symbol") or "")
        if symbol:
            grouped.setdefault(symbol, []).append(outcome)

    benchmark_reports = []
    for symbol, symbol_outcomes in sorted(
        grouped.items(),
        key=lambda item: local_benchmark_label(item[0]),
    ):
        horizons = []
        for horizon in DECISION_HORIZONS:
            observations = []
            for outcome in symbol_outcomes:
                result = (outcome.get("horizons") or {}).get(str(horizon))
                if not isinstance(result, dict) or result.get("status") != "complete":
                    continue
                observation = _local_observation(result)
                if observation is not None:
                    observations.append(observation)
            complete = len(observations)
            sufficient = complete >= min_mature_per_horizon
            horizons.append(
                {
                    "days": horizon,
                    "complete": complete,
                    "eligible": len(symbol_outcomes),
                    "minimum_required": min_mature_per_horizon,
                    "sufficient": sufficient,
                    "statistics": (
                        _benchmark_statistics(observations) if sufficient else None
                    ),
                }
            )
        benchmark_reports.append(
            {
                "symbol": symbol,
                "label": local_benchmark_label(symbol),
                "eligible_outcomes": len(symbol_outcomes),
                "errors": sum(
                    (outcome.get("local_benchmark") or {}).get("status") == "error"
                    for outcome in symbol_outcomes
                ),
                "cost_errors": sum(
                    (outcome.get("local_benchmark") or {}).get("cost_status")
                    == "error"
                    for outcome in symbol_outcomes
                ),
                "horizons": horizons,
            }
        )

    ready = bool(benchmark_reports) and all(
        next(item for item in benchmark["horizons"] if item["days"] == 40)[
            "sufficient"
        ]
        for benchmark in benchmark_reports
    )
    return {
        "status": "ready" if ready else "collecting",
        "status_label": (
            "Lokale referanser klare" if ready else "Lokale referanser samler data"
        ),
        "message": (
            "Lokale resultater er sekundær diagnostikk og endrer ikke ACWI-porten."
        ),
        "benchmarks": benchmark_reports,
    }


def _technical_reference_statistics(
    observations: list[dict[str, Any]],
) -> dict[str, float]:
    model_returns = [float(item["net_return_pct"]) for item in observations]
    reference_returns = [
        float(item["technical_reference_net_return_pct"])
        for item in observations
    ]
    differences = [
        float(item["model_vs_technical_net_return_pct"])
        for item in observations
    ]
    if len(differences) == 1:
        trimmed_differences = differences
    else:
        trim_count = min(
            len(differences) - 1,
            max(1, ceil(len(differences) * TOP_WINNER_TRIM_PCT / 100)),
        )
        trimmed_differences = sorted(differences)[:-trim_count]
    return {
        "average_model_net_return_pct": round(
            sum(model_returns) / len(model_returns),
            2,
        ),
        "average_reference_net_return_pct": round(
            sum(reference_returns) / len(reference_returns),
            2,
        ),
        "average_net_difference_pct": round(
            sum(differences) / len(differences),
            2,
        ),
        "median_net_difference_pct": round(median(differences), 2),
        "trimmed_average_net_difference_pct": round(
            sum(trimmed_differences) / len(trimmed_differences),
            2,
        ),
        "model_win_pct": round(
            sum(value > 0 for value in differences) / len(differences) * 100,
            1,
        ),
    }


def _build_technical_reference_report(
    outcomes: list[dict[str, Any]],
    *,
    min_mature_per_horizon: int,
) -> dict[str, Any]:
    eligible = [
        outcome
        for outcome in outcomes
        if outcome.get("action_code") in BENCHMARK_ELIGIBLE_ACTIONS
    ]
    classified = [
        outcome
        for outcome in eligible
        if (outcome.get("technical_reference") or {}).get("status") == "complete"
        and (outcome.get("technical_reference") or {}).get("action")
        in {"buy", "cash"}
    ]
    fingerprints = sorted(
        {
            str((outcome.get("technical_reference") or {}).get("rule_fingerprint"))
            for outcome in classified
            if (outcome.get("technical_reference") or {}).get("rule_fingerprint")
        }
    )
    rule_consistent = len(fingerprints) <= 1
    horizons = []
    for horizon in DECISION_HORIZONS:
        observations = []
        for outcome in classified:
            result = (outcome.get("horizons") or {}).get(str(horizon))
            required = (
                "net_return_pct",
                "technical_reference_net_return_pct",
                "model_vs_technical_net_return_pct",
            )
            if (
                isinstance(result, dict)
                and result.get("status") == "complete"
                and result.get("technical_reference_status") == "complete"
                and all(_finite(result.get(field)) is not None for field in required)
            ):
                observations.append(result)
        complete = len(observations)
        sufficient = complete >= min_mature_per_horizon and rule_consistent
        horizons.append(
            {
                "days": horizon,
                "complete": complete,
                "classified": len(classified),
                "minimum_required": min_mature_per_horizon,
                "sufficient": sufficient,
                "statistics": (
                    _technical_reference_statistics(observations)
                    if sufficient
                    else None
                ),
            }
        )

    complete_40d = next(item["complete"] for item in horizons if item["days"] == 40)
    ready = complete_40d >= min_mature_per_horizon and rule_consistent
    errors = sum(
        (outcome.get("technical_reference") or {}).get("evaluation_status")
        == "error"
        for outcome in classified
    )
    return {
        "version": TECHNICAL_REFERENCE_VERSION,
        "status": "ready" if ready else "collecting",
        "status_label": (
            "Teknisk referanse klar"
            if ready
            else "Teknisk referanse samler data"
        ),
        "message": (
            "Regelfingeravtrykkene er ulike; resultatene kan ikke slås sammen."
            if not rule_consistent
            else "Den enkle referansen er sekundær diagnostikk og påvirker ikke ACWI-porten."
        ),
        "eligible_outcomes": len(eligible),
        "classified_outcomes": len(classified),
        "unavailable_outcomes": len(eligible) - len(classified),
        "buy_signals": sum(
            (outcome.get("technical_reference") or {}).get("action") == "buy"
            for outcome in classified
        ),
        "cash_signals": sum(
            (outcome.get("technical_reference") or {}).get("action") == "cash"
            for outcome in classified
        ),
        "rule_fingerprints": fingerprints,
        "rule_consistent": rule_consistent,
        "errors": errors,
        "horizons": horizons,
    }


def _decision_gate(
    horizon_reports: list[dict[str, Any]],
    segments: dict[str, dict[str, Any]],
    *,
    ready: bool,
    cost_model_consistent: bool,
) -> dict[str, Any]:
    reports_by_day = {item["days"]: item for item in horizon_reports}
    checks = []

    def add_check(check_id, label, actual, operator, threshold):
        if operator == "gt":
            passed = actual is not None and actual > threshold
        elif operator == "gte":
            passed = actual is not None and actual >= threshold
        elif operator == "lte":
            passed = actual is not None and actual <= threshold
        else:
            raise ValueError(f"Ukjent beslutningsoperator: {operator}")
        checks.append(
            {
                "check_id": check_id,
                "label": label,
                "status": "pending" if not ready else "passed" if passed else "failed",
                "actual": actual,
                "operator": operator,
                "threshold": threshold,
            }
        )

    add_check(
        "cost_model_consistency",
        "Samme kostnadsmodell brukes for alle modne råd",
        1 if cost_model_consistent else 0,
        "gte",
        1,
    )
    for days in BENCHMARK_GATE_HORIZONS:
        statistics = reports_by_day[days].get("statistics") or {}
        add_check(
            f"positive_average_{days}d",
            f"Positiv gjennomsnittlig netto meravkastning etter {days} dager",
            statistics.get("average_net_relative_return_pct"),
            "gt",
            0.0,
        )
    for days in BENCHMARK_GATE_WIN_HORIZONS:
        statistics = reports_by_day[days].get("statistics") or {}
        add_check(
            f"majority_beats_acwi_{days}d",
            f"Mer enn halvparten slår ACWI netto etter {days} dager",
            statistics.get("net_benchmark_win_pct"),
            "gt",
            50.0,
        )
        add_check(
            f"non_negative_median_{days}d",
            f"Ikke-negativ median netto meravkastning etter {days} dager",
            statistics.get("median_net_relative_return_pct"),
            "gte",
            0.0,
        )
        add_check(
            f"positive_trimmed_average_{days}d",
            f"Positivt nettosnitt uten de øverste {TOP_WINNER_TRIM_PCT:g} % etter {days} dager",
            statistics.get("trimmed_average_net_relative_return_pct"),
            "gt",
            0.0,
        )

    for segment_key, label in (("regions", "regioner"), ("profiles", "profiler")):
        segment = segments[segment_key]
        add_check(
            f"{segment_key}_metadata_coverage",
            f"Minst {MIN_METADATA_COVERAGE_PCT:g} % metadata for {label}",
            segment["metadata_coverage_pct"],
            "gte",
            MIN_METADATA_COVERAGE_PCT,
        )
        add_check(
            f"{segment_key}_concentration",
            f"Ingen enkeltgruppe utgjør mer enn {MAX_SEGMENT_SHARE_PCT:g} %",
            segment["largest_share_pct"],
            "lte",
            MAX_SEGMENT_SHARE_PCT,
        )
        add_check(
            f"{segment_key}_breadth",
            f"Minst to {label} har positiv meravkastning",
            segment["positive_segments"],
            "gte",
            2,
        )

    passed = ready and all(item["status"] == "passed" for item in checks)
    status = "passed" if passed else "failed" if ready else "collecting"
    return {
        "version": BENCHMARK_DECISION_GATE_VERSION,
        "status": status,
        "status_label": {
            "collecting": "Beslutningsport: samler grunnlag",
            "passed": "Beslutningsport: bestått",
            "failed": "Beslutningsport: ikke bestått",
        }[status],
        "evaluated": ready,
        "message": (
            "Ingen konklusjon trekkes før 60 kjøpsråd har fullført 40 dager."
            if not ready
            else "Alle låste kriterier er oppfylt."
            if passed
            else "Minst ett låst kriterium er ikke oppfylt."
        ),
        "checks": checks,
    }


def _build_benchmark_report(
    outcomes: list[dict[str, Any]],
    *,
    min_mature_per_horizon: int,
    min_complete_40d: int,
) -> dict[str, Any]:
    eligible = [
        outcome
        for outcome in outcomes
        if outcome.get("action_code") in BENCHMARK_ELIGIBLE_ACTIONS
    ]
    horizon_reports = []
    observations_by_horizon: dict[int, list[dict[str, Any]]] = {}
    for horizon in DECISION_HORIZONS:
        observations = []
        for outcome in eligible:
            result = (outcome.get("horizons") or {}).get(str(horizon))
            if not isinstance(result, dict) or result.get("status") != "complete":
                continue
            required = (
                "return_pct",
                "benchmark_return_pct",
                "relative_return_pct",
                "net_return_pct",
                "benchmark_net_return_pct",
                "net_relative_return_pct",
            )
            if (
                result.get("benchmark_status") == "complete"
                and result.get("cost_status") == "complete"
                and all(_finite(result.get(field)) is not None for field in required)
            ):
                observations.append(
                    {
                        **result,
                        "region": outcome.get("region"),
                        "primary_profile": outcome.get("primary_profile"),
                        "cost_model_fingerprint": (
                            outcome.get("cost_evaluation") or {}
                        ).get("fingerprint"),
                    }
                )
        observations_by_horizon[horizon] = observations
        complete = len(observations)
        sufficient = complete >= min_mature_per_horizon
        horizon_reports.append(
            {
                "days": horizon,
                "complete": complete,
                "eligible": len(eligible),
                "coverage_pct": (
                    round(complete / len(eligible) * 100, 1) if eligible else 0.0
                ),
                "minimum_required": min_mature_per_horizon,
                "sufficient": sufficient,
                "statistics": (
                    _benchmark_statistics(observations) if sufficient else None
                ),
            }
        )

    complete_40d = next(
        item["complete"] for item in horizon_reports if item["days"] == 40
    )
    ready = complete_40d >= min_complete_40d
    benchmark_errors = sum(
        (outcome.get("benchmark") or {}).get("status") == "error"
        for outcome in eligible
    )
    cost_errors = sum(
        (outcome.get("cost_evaluation") or {}).get("status") == "error"
        for outcome in eligible
    )
    mature_40d = observations_by_horizon[40]
    cost_fingerprints = sorted(
        {
            str(item.get("cost_model_fingerprint"))
            for item in mature_40d
            if item.get("cost_model_fingerprint")
        }
    )
    cost_model_consistent = len(cost_fingerprints) == 1 if mature_40d else True
    segments = {
        "regions": _segment_report(mature_40d, "region"),
        "profiles": _segment_report(mature_40d, "primary_profile"),
    }
    decision_gate = _decision_gate(
        horizon_reports,
        segments,
        ready=ready,
        cost_model_consistent=cost_model_consistent,
    )
    cost_models = [
        outcome.get("cost_evaluation")
        for outcome in eligible
        if (outcome.get("cost_evaluation") or {}).get("status") == "complete"
    ]
    cost_model = cost_models[0] if cost_models else None
    return {
        "symbol": GLOBAL_EQUITY_BENCHMARK,
        "eligible_action_codes": sorted(BENCHMARK_ELIGIBLE_ACTIONS),
        "eligible_outcomes": len(eligible),
        "status": "ready" if ready else "collecting",
        "status_label": (
            "ACWI-grunnlag klart for vurdering" if ready else "Samler ACWI-data"
        ),
        "message": (
            "Kjøpsrådene kan nå vurderes relativt til ACWI."
            if ready
            else "ACWI-relative resultater vises først når nok kjøpsråd har nådd valgt horisont."
        ),
        "ready": ready,
        "complete_40d": complete_40d,
        "minimum_complete_40d": min_complete_40d,
        "errors": benchmark_errors,
        "cost_errors": cost_errors,
        "cost_model": (
            {
                "initial_capital": cost_model.get("initial_capital"),
                "fingerprint": cost_model.get("fingerprint"),
                "consistent": cost_model_consistent,
            }
            if cost_model
            else None
        ),
        "horizons": horizon_reports,
        "segments": segments,
        "decision_gate": decision_gate,
    }


def build_decision_outcome_report(
    outcomes: list[dict[str, Any]],
    *,
    min_mature_per_horizon: int = MIN_MATURE_OUTCOMES_PER_HORIZON,
    min_complete_40d: int = MIN_COMPLETE_40D_OUTCOMES,
) -> dict[str, Any]:
    """Build a descriptive report without drawing conclusions from thin data."""
    total = len(outcomes)
    horizon_reports = []
    for horizon in DECISION_HORIZONS:
        key = str(horizon)
        observations = []
        for outcome in outcomes:
            result = (outcome.get("horizons") or {}).get(key)
            if not isinstance(result, dict) or result.get("status") != "complete":
                continue
            required = ("return_pct", "max_favorable_pct", "max_adverse_pct")
            if all(_finite(result.get(field)) is not None for field in required):
                observations.append(result)

        complete = len(observations)
        sufficient = complete >= min_mature_per_horizon
        horizon_reports.append(
            {
                "days": horizon,
                "complete": complete,
                "total": total,
                "coverage_pct": round(complete / total * 100, 1) if total else 0.0,
                "minimum_required": min_mature_per_horizon,
                "sufficient": sufficient,
                "statistics": _horizon_statistics(observations) if sufficient else None,
            }
        )

    complete_40d = next(
        item["complete"] for item in horizon_reports if item["days"] == 40
    )
    overall_ready = complete_40d >= min_complete_40d
    action_counts: dict[str, dict[str, int]] = {}
    for outcome in outcomes:
        action = str(outcome.get("action_code") or "unknown")
        counts = action_counts.setdefault(action, {"total": 0, "complete_40d": 0})
        counts["total"] += 1
        horizon_40 = (outcome.get("horizons") or {}).get("40") or {}
        if horizon_40.get("status") == "complete":
            counts["complete_40d"] += 1

    return {
        "status": "ready" if overall_ready else "collecting",
        "status_label": (
            "Datagrunnlag klart for vurdering" if overall_ready else "For lite data"
        ),
        "message": (
            "40-dagersgrunnlaget kan nå vurderes sammen med referansene."
            if overall_ready
            else "Resultater vises først når nok råd har nådd valgt horisont."
        ),
        "overall_ready": overall_ready,
        "complete_40d": complete_40d,
        "minimum_complete_40d": min_complete_40d,
        "horizons": horizon_reports,
        "actions": [
            {"action_code": action, **counts}
            for action, counts in sorted(action_counts.items())
        ],
        "benchmark": _build_benchmark_report(
            outcomes,
            min_mature_per_horizon=min_mature_per_horizon,
            min_complete_40d=min_complete_40d,
        ),
        "local_benchmarks": _build_local_benchmark_report(
            outcomes,
            min_mature_per_horizon=min_mature_per_horizon,
        ),
        "technical_reference": _build_technical_reference_report(
            outcomes,
            min_mature_per_horizon=min_mature_per_horizon,
        ),
    }
