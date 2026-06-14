from __future__ import annotations

import time
from datetime import date, datetime, timezone
from typing import Any

from src.analyst import get_analyst
from src.config import load_watchlists
from src.context import build_agent_context, save_context_snapshot
from src.data import get_daily_prices
from src.earnings import get_earnings
from src.fundamental_history import analyze_fundamental_history
from src.fundamentals import get_fundamentals
from src.indicators import add_indicators
from src.model_backtest import save_model_snapshot
from src.news import build_news_summary, get_news
from src.research_ideas import load_research_ideas
from src.screener import screen_nordics, screen_obx, screen_us_large
from src.sentiment import build_sentiment_summary
from src.storage import load_pending_orders, load_portfolio
from src.technicals import analyze_technicals, get_benchmark_for_symbol


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


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
        get_earnings(symbol, use_cache=use_cache, today=today)
    except Exception as exc:
        _record_error(errors, symbol, "earnings", exc)


def _refresh_analyst(
    symbol: str,
    errors: list[dict[str, str]],
    use_cache: bool = True,
    today: date | None = None,
) -> None:
    try:
        get_analyst(symbol, use_cache=use_cache, today=today)
    except Exception as exc:
        _record_error(errors, symbol, "analyst", exc)


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


def _run_screeners(
    errors: list[dict[str, str]],
    pause_seconds: float,
    watchlists: dict[str, list[str]],
) -> None:
    screeners = (
        ("screening_usa", screen_us_large),
        ("screening_nordics", screen_nordics),
        ("screening_obx", screen_obx),
    )

    for step_name, screen_fn in screeners:
        try:
            screen_fn(
                pause_seconds=pause_seconds,
                existing_watchlists=watchlists,
            )
        except Exception as exc:
            _record_error(errors, None, step_name, exc)


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

    screening_updated = False
    try:
        _run_screeners(errors, pause_seconds, watchlists)
        screening_updated = True
    except Exception as exc:
        _record_error(errors, None, "screening", exc)

    context = None
    snapshot_updated = False
    try:
        context = build_agent_context(
            watchlist_symbols,
            portfolio=portfolio,
            pending_orders=load_pending_orders([]),
            research_ideas=load_research_ideas(),
            pause_seconds=pause_seconds,
        )
        save_model_snapshot(watchlist_symbols)
        save_context_snapshot(context, today=today)
        snapshot_updated = True
    except Exception as exc:
        _record_error(errors, None, "context_snapshot", exc)

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
        "errors": errors,
    }


def build_refresh_summary(result: dict[str, Any]) -> str:
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


def main() -> int:
    result = run_daily_refresh()
    print(build_refresh_summary(result))

    if not result.get("success"):
        _print_refresh_errors(result)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
