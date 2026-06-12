import json
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

SOURCE_YFINANCE = "yfinance"

STATUS_CONFIRMED = "confirmed"
STATUS_ESTIMATED = "estimated"
STATUS_UNKNOWN = "unknown"


def _project_root():
    return Path(__file__).resolve().parent.parent


def _cache_dir():
    cache_dir = _project_root() / "cache"
    cache_dir.mkdir(exist_ok=True)
    return cache_dir


def _cache_file(symbol):
    return _cache_dir() / f"{symbol}_earnings.json"


def _utc_now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize_earnings_date(value, today=None):
    if value is None:
        return None

    if isinstance(value, list):
        dates = [
            normalized
            for item in value
            for normalized in [normalize_earnings_date(item, today=today)]
            if normalized
        ]
        if not dates:
            return None
        today = today or date.today()
        today_iso = today.isoformat()
        future = [item for item in dates if item >= today_iso]
        if future:
            return min(future)
        return min(dates)

    if isinstance(value, pd.Timestamp):
        return value.date().isoformat()

    if isinstance(value, datetime):
        return value.date().isoformat()

    if isinstance(value, date):
        return value.isoformat()

    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc).date().isoformat()

    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
        except ValueError:
            pass
        try:
            return date.fromisoformat(text[:10]).isoformat()
        except ValueError:
            return None

    return None


def compute_days_until(earnings_date, today=None):
    normalized = normalize_earnings_date(earnings_date, today=today)
    if not normalized:
        return None

    today = today or date.today()
    earnings = date.fromisoformat(normalized)
    return (earnings - today).days


def determine_status(earnings_date, is_estimate=None):
    if not normalize_earnings_date(earnings_date):
        return STATUS_UNKNOWN

    if is_estimate is True:
        return STATUS_ESTIMATED

    if is_estimate is False:
        return STATUS_CONFIRMED

    return STATUS_ESTIMATED


def _extract_calendar_earnings_date(calendar):
    if calendar is None:
        return None

    if isinstance(calendar, dict):
        return normalize_earnings_date(calendar.get("Earnings Date"))

    if hasattr(calendar, "get"):
        try:
            return normalize_earnings_date(calendar.get("Earnings Date"))
        except (TypeError, AttributeError):
            return None

    return None


def _fetch_yfinance_earnings(symbol):
    print(f"Henter earnings for {symbol}")

    stock = yf.Ticker(symbol)
    earnings_date = None
    is_estimate = None

    try:
        earnings_date = _extract_calendar_earnings_date(stock.calendar)
    except Exception:
        earnings_date = None

    try:
        info = stock.info or {}
        if earnings_date is None:
            timestamp = info.get("earningsTimestampStart") or info.get(
                "earningsTimestamp"
            )
            earnings_date = normalize_earnings_date(timestamp)

        if "isEarningsDateEstimate" in info:
            is_estimate = info.get("isEarningsDateEstimate")
    except Exception:
        pass

    status = determine_status(earnings_date, is_estimate=is_estimate)
    earnings_date = normalize_earnings_date(earnings_date)

    return {
        "ticker": symbol,
        "earnings_date": earnings_date,
        "days_until": compute_days_until(earnings_date),
        "status": status,
        "source": SOURCE_YFINANCE,
        "last_updated": _utc_now_iso(),
    }


def _write_earnings_cache(cache_file, symbol, data, today=None):
    today = (today or date.today()).isoformat()
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(
            {
                "date": today,
                "symbol": symbol,
                "source": SOURCE_YFINANCE,
                "data": data,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )


def _refresh_cached_days_until(data, today=None):
    refreshed = dict(data)
    earnings_date = refreshed.get("earnings_date")
    refreshed["days_until"] = compute_days_until(earnings_date, today=today)
    if not earnings_date:
        refreshed["status"] = STATUS_UNKNOWN
    return refreshed


def get_earnings(symbol, use_cache=True, today=None):
    today = today or date.today()
    today_iso = today.isoformat()
    symbol = str(symbol).strip().upper()
    cache_file = _cache_file(symbol)

    if use_cache and cache_file.exists():
        with open(cache_file, "r", encoding="utf-8") as f:
            cached = json.load(f)

        if cached.get("date") == today_iso:
            print(f"Bruker earnings-cache for {symbol}")
            return _refresh_cached_days_until(cached["data"], today=today)

    data = _fetch_yfinance_earnings(symbol)
    _write_earnings_cache(cache_file, symbol, data, today=today)
    return data


def _ordered_universe_tickers(portfolio, watchlist):
    portfolio_tickers = []
    portfolio_set = set()

    for position in portfolio or []:
        ticker = str(position.get("ticker", "")).strip().upper()
        if not ticker or ticker in portfolio_set:
            continue
        portfolio_set.add(ticker)
        portfolio_tickers.append(ticker)

    watchlist_tickers = []
    for ticker in watchlist or []:
        normalized = str(ticker).strip().upper()
        if not normalized or normalized in portfolio_set:
            continue
        if normalized not in watchlist_tickers:
            watchlist_tickers.append(normalized)

    return portfolio_tickers + watchlist_tickers, portfolio_set


def sort_earnings_items(items, portfolio_tickers):
    portfolio_set = {
        str(ticker).strip().upper()
        for ticker in (portfolio_tickers or [])
        if ticker
    }

    def sort_key(item):
        in_portfolio = item.get("ticker") in portfolio_set
        days_until = item.get("days_until")
        if days_until is None:
            days_sort = 10_000
        else:
            days_sort = days_until
        return (
            0 if in_portfolio else 1,
            days_sort,
            item.get("ticker", ""),
        )

    return sorted(items, key=sort_key)


def build_earnings_summary(portfolio=None, watchlist=None, use_cache=True, today=None):
    today = today or date.today()
    tickers, portfolio_set = _ordered_universe_tickers(portfolio, watchlist)

    items = []
    for ticker in tickers:
        item = get_earnings(ticker, use_cache=use_cache, today=today)
        item = dict(item)
        item["in_portfolio"] = ticker in portfolio_set
        items.append(item)

    items = sort_earnings_items(items, portfolio_set)
    unknown = [item for item in items if item.get("status") == STATUS_UNKNOWN]
    upcoming_14_days = [
        item
        for item in items
        if item.get("days_until") is not None
        and 0 <= item["days_until"] <= 14
    ]

    last_updated_values = [item.get("last_updated") for item in items if item.get("last_updated")]
    last_updated = max(last_updated_values) if last_updated_values else _utc_now_iso()

    return {
        "items": items,
        "upcoming_14_days": upcoming_14_days,
        "unknown": unknown,
        "last_updated": last_updated,
    }


def build_earnings_table(earnings_summary):
    rows = []
    for item in earnings_summary.get("items") or []:
        days_until = item.get("days_until")
        rows.append(
            {
                "Ticker": item.get("ticker", ""),
                "Dato": item.get("earnings_date") or "—",
                "Dager": days_until if days_until is not None else "—",
                "Status": item.get("status", STATUS_UNKNOWN),
                "Kilde": item.get("source", SOURCE_YFINANCE),
            }
        )

    return pd.DataFrame(rows)
