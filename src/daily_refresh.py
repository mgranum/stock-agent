from __future__ import annotations

import argparse
import fcntl
import json
import os
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from src.analyst import get_analyst
from src.config import load_watchlists
from src.environment import (
    daily_refresh_lock_filename,
    daily_refresh_state_filename,
)
from src.context import (
    _parse_iso_datetime,
    build_agent_context,
    get_context_snapshot_metadata,
    save_context_snapshot,
)
from src.data import get_daily_prices
from src.earnings import get_earnings
from src.fundamental_history import analyze_fundamental_history
from src.fundamentals import get_fundamentals
from src.indicators import add_indicators
from src.model_backtest import save_model_snapshot
from src.discovery_validation import save_discovery_journal
from src.decision_journal import save_decision_journal
from src.news import build_news_summary, get_news
from src.network import check_network_ready
from src.research_ideas import load_research_ideas
from src.sentiment import build_sentiment_summary
from src.storage import load_portfolio
from src.storage import atomic_write_json
from src.technicals import analyze_technicals, get_benchmark_for_symbol

_lock_file_handle: Any | None = None

NETWORK_PREFLIGHT_RETRIES = 3
NETWORK_PREFLIGHT_RETRY_DELAY_SECONDS = 60.0
NETWORK_SKIP_REASON = "network_unavailable"


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _cache_dir() -> Path:
    cache_dir = _project_root() / "cache"
    cache_dir.mkdir(exist_ok=True)
    return cache_dir


def refresh_state_path() -> Path:
    return _cache_dir() / daily_refresh_state_filename()


def refresh_lock_path() -> Path:
    return _cache_dir() / daily_refresh_lock_filename()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _format_display_datetime(value: Any) -> str | None:
    parsed = _parse_iso_datetime(value)
    if parsed is None:
        return None
    return parsed.astimezone().strftime("%Y-%m-%d %H:%M")


def load_refresh_state() -> dict[str, Any] | None:
    path = refresh_state_path()
    if not path.exists():
        return None

    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None

    if not isinstance(payload, dict):
        return None

    return payload


def save_refresh_state(state: dict[str, Any]) -> Path:
    path = refresh_state_path()
    return atomic_write_json(path, state)


def should_run_refresh(
    today: date | None = None,
    force: bool = False,
) -> bool:
    if force:
        return True

    today = today or date.today()
    state = load_refresh_state()
    if state is None:
        return True

    last_successful_date = state.get("last_successful_date")
    last_status = state.get("last_status")

    if (
        last_successful_date == today.isoformat()
        and last_status == "success"
    ):
        return False

    return True


def acquire_refresh_lock() -> bool:
    global _lock_file_handle

    path = refresh_lock_path()
    handle = open(path, "w", encoding="utf-8")

    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        return False

    handle.seek(0)
    handle.write(str(os.getpid()))
    handle.truncate()
    handle.flush()
    _lock_file_handle = handle
    return True


def release_refresh_lock() -> None:
    global _lock_file_handle

    if _lock_file_handle is None:
        return

    try:
        fcntl.flock(_lock_file_handle.fileno(), fcntl.LOCK_UN)
        _lock_file_handle.close()
    finally:
        _lock_file_handle = None


def format_refresh_panel_status(
    refresh_state: dict[str, Any] | None = None,
    snapshot_metadata: dict[str, Any] | None = None,
    today: date | None = None,
) -> dict[str, str]:
    today = today or date.today()
    today_iso = today.isoformat()

    if refresh_state is None:
        refresh_state = load_refresh_state()
    if snapshot_metadata is None:
        snapshot_metadata = get_context_snapshot_metadata()

    updated_at = None
    updated_at_source = "unknown"

    if refresh_state and refresh_state.get("last_finished_at"):
        updated_at = _format_display_datetime(refresh_state.get("last_finished_at"))
        updated_at_source = "refresh_state"
    elif snapshot_metadata and snapshot_metadata.get("built_at"):
        updated_at = _format_display_datetime(snapshot_metadata.get("built_at"))
        updated_at_source = "snapshot"

    status = "unknown"
    status_label = "Ukjent"

    if refresh_state:
        last_status = refresh_state.get("last_status")
        last_successful_date = refresh_state.get("last_successful_date")

        if (
            last_successful_date == today_iso
            and last_status == "success"
        ):
            status = "ok"
            status_label = "OK"
        elif last_status == "failed":
            status = "failed"
            status_label = "Feilet"
        elif last_status == "skipped_network":
            status = "skipped_network"
            status_label = "Nettverksfeil – bruker siste vellykkede data"
        elif last_successful_date != today_iso:
            status = "stale"
            status_label = "Ikke oppdatert i dag"
    elif snapshot_metadata:
        snapshot_date = snapshot_metadata.get("date")
        if snapshot_date == today_iso:
            status = "ok"
            status_label = "OK"
        else:
            status = "stale"
            status_label = "Ikke oppdatert i dag"

    return {
        "updated_at": updated_at or "–",
        "updated_at_source": updated_at_source,
        "status": status,
        "status_label": status_label,
    }


def _build_refresh_state(
    *,
    last_successful_date: str | None = None,
    last_started_at: str | None = None,
    last_finished_at: str | None = None,
    last_status: str,
    last_error_count: int = 0,
    duration_seconds: float | None = None,
    previous: dict[str, Any] | None = None,
) -> dict[str, Any]:
    previous = previous or {}

    return {
        "last_successful_date": last_successful_date,
        "last_started_at": last_started_at,
        "last_finished_at": last_finished_at,
        "last_status": last_status,
        "last_error_count": last_error_count,
        "duration_seconds": duration_seconds,
    }


def _record_error(
    errors: list[dict[str, str]],
    symbol: str | None,
    step: str,
    exc: Exception,
) -> None:
    errors.append({
        "symbol": symbol or "",
        "step": step,
        "error": str(exc),
    })


def _collect_refresh_symbols(
    watchlist_symbols: list[str],
    portfolio: list[dict[str, Any]],
) -> list[str]:
    symbols: list[str] = []
    seen: set[str] = set()

    for position in portfolio or []:
        ticker = str(position.get("ticker", "")).strip().upper()
        if not ticker or ticker in seen:
            continue
        seen.add(ticker)
        symbols.append(ticker)

    for ticker in watchlist_symbols or []:
        normalized = str(ticker).strip().upper()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        symbols.append(normalized)

    return symbols


def _refresh_technicals(
    symbol: str,
    errors: list[dict[str, str]],
    use_cache: bool = True,
) -> None:
    try:
        df = get_daily_prices(symbol, use_cache=use_cache)
        df = add_indicators(df)
        benchmark_symbol = get_benchmark_for_symbol(symbol)
        benchmark_df = add_indicators(
            get_daily_prices(benchmark_symbol, use_cache=use_cache)
        )
        analyze_technicals(df, benchmark_df, benchmark_symbol)
    except Exception as exc:
        _record_error(errors, symbol, "technicals", exc)


def _refresh_fundamentals(
    symbol: str,
    errors: list[dict[str, str]],
    use_cache: bool = True,
) -> None:
    try:
        get_fundamentals(symbol, use_cache=use_cache)
    except Exception as exc:
        _record_error(errors, symbol, "fundamentals", exc)


def _refresh_fundamental_history(
    symbol: str,
    errors: list[dict[str, str]],
) -> None:
    try:
        analyze_fundamental_history(symbol)
    except Exception as exc:
        _record_error(errors, symbol, "fundamental_history", exc)


def _refresh_earnings(
    symbol: str,
    errors: list[dict[str, str]],
    use_cache: bool = True,
    today: date | None = None,
) -> None:
    try:
        result = get_earnings(symbol, use_cache=use_cache, today=today)
    except Exception as exc:
        _record_error(errors, symbol, "earnings", exc)
        return

    fetch_error = result.get("fetch_error") if isinstance(result, dict) else None
    if isinstance(fetch_error, str) and fetch_error:
        _record_error(errors, symbol, "earnings", Exception(fetch_error))


def _refresh_analyst(
    symbol: str,
    errors: list[dict[str, str]],
    use_cache: bool = True,
    today: date | None = None,
) -> None:
    try:
        result = get_analyst(symbol, use_cache=use_cache, today=today)
    except Exception as exc:
        _record_error(errors, symbol, "analyst", exc)
        return

    fetch_error = result.get("fetch_error") if isinstance(result, dict) else None
    if isinstance(fetch_error, str) and fetch_error:
        _record_error(errors, symbol, "analyst", Exception(fetch_error))


def _refresh_news(
    symbol: str,
    errors: list[dict[str, str]],
    use_cache: bool = True,
    today: date | None = None,
) -> None:
    try:
        get_news(symbol, use_cache=use_cache, today=today)
    except Exception as exc:
        _record_error(errors, symbol, "news", exc)


def run_daily_refresh(
    pause_seconds: float = 1,
    use_cache: bool = True,
    today: date | None = None,
) -> dict[str, Any]:
    started_at = _utc_now_iso()
    start_time = time.monotonic()
    today = today or date.today()
    errors: list[dict[str, str]] = []

    watchlists = load_watchlists()
    watchlist_symbols = list(watchlists.get("Alle") or [])
    portfolio = load_portfolio([])
    symbols = _collect_refresh_symbols(watchlist_symbols, portfolio)

    for i, symbol in enumerate(symbols, start=1):
        _refresh_technicals(symbol, errors, use_cache=use_cache)
        _refresh_fundamentals(symbol, errors, use_cache=use_cache)
        _refresh_fundamental_history(symbol, errors)
        _refresh_earnings(symbol, errors, use_cache=use_cache, today=today)
        _refresh_analyst(symbol, errors, use_cache=use_cache, today=today)
        _refresh_news(symbol, errors, use_cache=use_cache, today=today)

        if pause_seconds and i < len(symbols):
            time.sleep(pause_seconds)

    sentiment_updated = False
    try:
        news_summary = build_news_summary(
            portfolio=portfolio,
            watchlist=watchlist_symbols,
            use_cache=use_cache,
            today=today,
        )
        build_sentiment_summary(news_summary)
        sentiment_updated = True
    except Exception as exc:
        _record_error(errors, None, "sentiment", exc)

    context = None
    snapshot_updated = False
    try:
        context = build_agent_context(
            watchlist_symbols,
            portfolio=portfolio,
            research_ideas=load_research_ideas(),
            pause_seconds=pause_seconds,
        )
        save_model_snapshot(watchlist_symbols)
        save_context_snapshot(context, today=today)
        snapshot_updated = True
    except Exception as exc:
        _record_error(errors, None, "context_snapshot", exc)

    discovery_journal_updated = False
    decision_journal_updated = False
    if context is not None:
        try:
            discovery_journal_updated = bool(
                save_discovery_journal(context, signal_date=today)
            )
        except Exception as exc:
            _record_error(errors, None, "discovery_journal", exc)
        try:
            decision_journal_updated = bool(
                save_decision_journal(
                    context,
                    signal_date=today,
                    recorded_at=_parse_iso_datetime(started_at),
                )
            )
        except Exception as exc:
            _record_error(errors, None, "decision_journal", exc)

    screening_updated = bool(
        context is not None
        and isinstance(context.get("screening_results"), dict)
    )

    finished_at = _utc_now_iso()
    duration_seconds = round(time.monotonic() - start_time, 2)

    return {
        "success": len(errors) == 0,
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_seconds": duration_seconds,
        "symbols_processed": len(symbols),
        "portfolio_positions": len(portfolio),
        "watchlist_symbols": len(watchlist_symbols),
        "earnings_updated": True,
        "analyst_updated": True,
        "news_updated": True,
        "sentiment_updated": sentiment_updated,
        "screening_updated": screening_updated,
        "snapshot_updated": snapshot_updated,
        "discovery_journal_updated": discovery_journal_updated,
        "decision_journal_updated": decision_journal_updated,
        "errors": errors,
    }


def wait_for_network_ready(
    *,
    retries: int = NETWORK_PREFLIGHT_RETRIES,
    retry_delay_seconds: float = NETWORK_PREFLIGHT_RETRY_DELAY_SECONDS,
    sleep_fn=time.sleep,
    check_fn=None,
) -> tuple[bool, str | None]:
    check = check_fn or check_network_ready
    last_error: str | None = None

    for attempt in range(1, retries + 1):
        ready, error = check()
        if ready:
            return True, None

        last_error = error
        if attempt < retries:
            sleep_fn(retry_delay_seconds)

    return False, last_error


def build_refresh_summary(result: dict[str, Any]) -> str:
    if result.get("skipped_network"):
        message = result.get("message") or (
            "Daily Refresh hoppet over: nettverk utilgjengelig."
        )
        return message

    if result.get("skipped"):
        message = str(result.get("message") or "Daily Refresh hoppet over.")
        if result.get("dry_run") and "network_ready" in result:
            network_label = (
                "klart" if result.get("network_ready") else "utilgjengelig"
            )
            return f"{message}\n\nNettverk: {network_label}."
        return message

    lines = [
        "Daily Refresh Fullført",
        "",
        f"- {result.get('symbols_processed', 0)} symboler analysert",
        f"- {result.get('portfolio_positions', 0)} porteføljeposisjoner",
    ]

    if result.get("earnings_updated"):
        lines.append("- Earnings oppdatert")

    if result.get("analyst_updated"):
        lines.append("- Analyst consensus oppdatert")

    if result.get("news_updated"):
        lines.append("- News oppdatert")

    if result.get("sentiment_updated"):
        lines.append("- Sentiment oppdatert")

    if result.get("screening_updated"):
        lines.append("- Screening oppdatert")

    if result.get("snapshot_updated"):
        lines.append("- Dashboard/context snapshot oppdatert")

    if result.get("discovery_journal_updated"):
        lines.append("- Discovery-valideringsjournal oppdatert")

    if result.get("decision_journal_updated"):
        lines.append("- Beslutningsjournal oppdatert")

    error_count = len(result.get("errors") or [])
    if error_count:
        lines.extend([
            "",
            f"- {error_count} feil under oppdatering",
        ])

    return "\n".join(lines)


def _print_refresh_errors(result: dict[str, Any]) -> None:
    errors = result.get("errors") or []
    if not errors:
        return

    print("")
    print("Feil:")
    for error in errors:
        symbol = error.get("symbol") or "-"
        step = error.get("step") or "unknown"
        message = error.get("error") or "ukjent feil"
        print(f"- {symbol} ({step}): {message}")


def _save_running_state(previous: dict[str, Any] | None, started_at: str) -> None:
    previous = previous or {}
    save_refresh_state(_build_refresh_state(
        last_successful_date=previous.get("last_successful_date"),
        last_started_at=started_at,
        last_finished_at=previous.get("last_finished_at"),
        last_status="running",
        last_error_count=previous.get("last_error_count", 0),
        duration_seconds=previous.get("duration_seconds"),
    ))


def _save_finished_state(
    result: dict[str, Any],
    *,
    today: date,
    previous: dict[str, Any] | None,
) -> None:
    previous = previous or {}
    error_count = len(result.get("errors") or [])
    success = bool(result.get("success"))

    save_refresh_state(_build_refresh_state(
        last_successful_date=(
            today.isoformat()
            if success
            else previous.get("last_successful_date")
        ),
        last_started_at=result.get("started_at"),
        last_finished_at=result.get("finished_at"),
        last_status="success" if success else "failed",
        last_error_count=error_count,
        duration_seconds=result.get("duration_seconds"),
    ))


def _save_skipped_network_state(
    *,
    error: str,
    previous: dict[str, Any] | None = None,
) -> dict[str, Any]:
    previous = previous or {}
    finished_at = _utc_now_iso()
    save_refresh_state(_build_refresh_state(
        last_successful_date=previous.get("last_successful_date"),
        last_started_at=finished_at,
        last_finished_at=finished_at,
        last_status="skipped_network",
        last_error_count=1,
        duration_seconds=0,
    ))
    message = (
        "Daily Refresh hoppet over: nettverk utilgjengelig. "
        f"{error}"
    )
    return {
        "success": True,
        "skipped": True,
        "skipped_network": True,
        "reason": NETWORK_SKIP_REASON,
        "message": message,
        "network_error": error,
        "finished_at": finished_at,
        "errors": [],
    }


def _save_skipped_state(
    *,
    reason: str,
    previous: dict[str, Any] | None = None,
) -> dict[str, Any]:
    previous = previous or {}
    finished_at = _utc_now_iso()
    save_refresh_state(_build_refresh_state(
        last_successful_date=previous.get("last_successful_date"),
        last_started_at=previous.get("last_started_at"),
        last_finished_at=finished_at,
        last_status="skipped",
        last_error_count=previous.get("last_error_count", 0),
        duration_seconds=previous.get("duration_seconds"),
    ))
    return {
        "success": True,
        "skipped": True,
        "reason": reason,
        "message": reason,
        "finished_at": finished_at,
        "errors": [],
    }


def execute_daily_refresh(
    *,
    force: bool = False,
    dry_run: bool = False,
    today: date | None = None,
    network_retries: int = NETWORK_PREFLIGHT_RETRIES,
    network_retry_delay_seconds: float = NETWORK_PREFLIGHT_RETRY_DELAY_SECONDS,
) -> dict[str, Any]:
    today = today or date.today()
    previous = load_refresh_state()

    if not should_run_refresh(today=today, force=force):
        reason = "Daily Refresh hoppet over: allerede kjørt i dag."
        if dry_run:
            network_ready, network_error = check_network_ready()
            return {
                "success": True,
                "skipped": True,
                "dry_run": True,
                "reason": reason,
                "message": reason,
                "network_ready": network_ready,
                "network_error": network_error,
                "errors": [],
            }
        return _save_skipped_state(reason=reason, previous=previous)

    if not acquire_refresh_lock():
        reason = "Daily Refresh hoppet over: kjøring pågår allerede."
        if dry_run:
            network_ready, network_error = check_network_ready()
            return {
                "success": True,
                "skipped": True,
                "dry_run": True,
                "reason": reason,
                "message": reason,
                "network_ready": network_ready,
                "network_error": network_error,
                "errors": [],
            }
        return _save_skipped_state(reason=reason, previous=previous)

    if dry_run:
        release_refresh_lock()
        network_ready, network_error = check_network_ready()
        message = "Daily Refresh dry-run: ville kjørt refresh nå."
        return {
            "success": True,
            "skipped": True,
            "dry_run": True,
            "reason": message,
            "message": message,
            "network_ready": network_ready,
            "network_error": network_error,
            "errors": [],
        }

    network_ready, network_error = wait_for_network_ready(
        retries=network_retries,
        retry_delay_seconds=network_retry_delay_seconds,
    )
    if not network_ready:
        result = _save_skipped_network_state(
            error=network_error or "Network preflight failed",
            previous=previous,
        )
        release_refresh_lock()
        return result

    started_at = _utc_now_iso()
    _save_running_state(previous, started_at)

    try:
        result = run_daily_refresh(today=today)
        _save_finished_state(result, today=today, previous=previous)
        return result
    except Exception:
        finished_at = _utc_now_iso()
        save_refresh_state(_build_refresh_state(
            last_successful_date=previous.get("last_successful_date"),
            last_started_at=started_at,
            last_finished_at=finished_at,
            last_status="failed",
            last_error_count=0,
            duration_seconds=None,
        ))
        raise
    finally:
        release_refresh_lock()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Kjør daglig dataoppdatering.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Kjør refresh selv om dagens kjøring allerede er fullført.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Vis om refresh ville kjørt uten å hente data.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = execute_daily_refresh(force=args.force, dry_run=args.dry_run)
    print(build_refresh_summary(result))

    if result.get("skipped"):
        return 0

    if result.get("skipped_network"):
        return 0

    if not result.get("success"):
        _print_refresh_errors(result)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
