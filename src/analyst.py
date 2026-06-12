import json
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

SOURCE_YFINANCE = "yfinance"

RECOMMENDATION_LABELS = {
    "strong_buy": "Sterk kjøp",
    "buy": "Kjøp",
    "hold": "Hold",
    "sell": "Selg",
    "strong_sell": "Sterk selg",
    "underperform": "Underperform",
    "outperform": "Outperform",
}

DISCLAIMER = (
    "Analytikerkonsensus er et støttesignal og påvirker ikke anbefalingene."
)


def _project_root():
    return Path(__file__).resolve().parent.parent


def _cache_dir():
    cache_dir = _project_root() / "cache"
    cache_dir.mkdir(exist_ok=True)
    return cache_dir


def _cache_file(symbol):
    return _cache_dir() / f"{symbol}_analyst.json"


def _utc_now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe_number(value):
    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value):
    number = _safe_number(value)
    if number is None:
        return None
    return int(number)


def compute_upside_pct(current_price, target_mean):
    current = _safe_number(current_price)
    target = _safe_number(target_mean)

    if current is None or target is None or current <= 0:
        return None

    return round(((target - current) / current) * 100, 1)


def format_recommendation_label(recommendation_key):
    if not recommendation_key:
        return "—"

    key = str(recommendation_key).strip().lower()
    return RECOMMENDATION_LABELS.get(key, key.replace("_", " ").title())


def _extract_distribution(recommendations_summary):
    if recommendations_summary is None:
        return None

    if hasattr(recommendations_summary, "empty") and recommendations_summary.empty:
        return None

    current = recommendations_summary
    if "period" in current.columns:
        matched = current[current["period"] == "0m"]
        if not matched.empty:
            current = matched
        else:
            current = current.iloc[[0]]

    row = current.iloc[0]
    distribution = {
        "strong_buy": _safe_int(row.get("strongBuy")),
        "buy": _safe_int(row.get("buy")),
        "hold": _safe_int(row.get("hold")),
        "sell": _safe_int(row.get("sell")),
        "strong_sell": _safe_int(row.get("strongSell")),
    }

    if all(value is None for value in distribution.values()):
        return None

    return distribution


def _has_analyst_data(data):
    return any(
        data.get(field) is not None
        for field in (
            "analyst_count",
            "target_mean",
            "recommendation_key",
            "recommendation_mean",
        )
    )


def _fetch_yfinance_analyst(symbol):
    print(f"Henter analytikerkonsensus for {symbol}")

    stock = yf.Ticker(symbol)
    info = {}

    try:
        info = stock.info or {}
    except Exception:
        info = {}

    recommendations_summary = None
    try:
        recommendations_summary = stock.recommendations_summary
    except Exception:
        recommendations_summary = None

    data = {
        "ticker": symbol,
        "recommendation_key": info.get("recommendationKey"),
        "recommendation_mean": _safe_number(info.get("recommendationMean")),
        "analyst_count": _safe_int(info.get("numberOfAnalystOpinions")),
        "target_mean": _safe_number(info.get("targetMeanPrice")),
        "target_median": _safe_number(info.get("targetMedianPrice")),
        "target_high": _safe_number(info.get("targetHighPrice")),
        "target_low": _safe_number(info.get("targetLowPrice")),
        "current_price": _safe_number(info.get("currentPrice")),
        "currency": info.get("currency"),
        "distribution": _extract_distribution(recommendations_summary),
        "source": SOURCE_YFINANCE,
        "last_updated": _utc_now_iso(),
    }
    data["upside_pct"] = compute_upside_pct(
        data["current_price"],
        data["target_mean"],
    )
    return data


def _write_analyst_cache(cache_file, symbol, data, today=None):
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


def get_analyst(symbol, use_cache=True, today=None):
    today = today or date.today()
    today_iso = today.isoformat()
    symbol = str(symbol).strip().upper()
    cache_file = _cache_file(symbol)

    if use_cache and cache_file.exists():
        with open(cache_file, "r", encoding="utf-8") as f:
            cached = json.load(f)

        if cached.get("date") == today_iso:
            print(f"Bruker analyst-cache for {symbol}")
            return dict(cached["data"])

    data = _fetch_yfinance_analyst(symbol)
    _write_analyst_cache(cache_file, symbol, data, today=today)
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


def sort_analyst_items(items, portfolio_set):
    portfolio_set = {
        str(ticker).strip().upper()
        for ticker in (portfolio_set or [])
        if ticker
    }

    def sort_key(item):
        in_portfolio = item.get("ticker") in portfolio_set
        analyst_count = item.get("analyst_count")
        count_sort = analyst_count if analyst_count is not None else -1
        return (
            0 if in_portfolio else 1,
            -count_sort,
            item.get("ticker", ""),
        )

    return sorted(items, key=sort_key)


def build_analyst_summary(portfolio=None, watchlist=None, use_cache=True, today=None):
    today = today or date.today()
    tickers, portfolio_set = _ordered_universe_tickers(portfolio, watchlist)

    items = []
    missing_data = []

    for ticker in tickers:
        item = get_analyst(ticker, use_cache=use_cache, today=today)
        item = dict(item)
        item["in_portfolio"] = ticker in portfolio_set
        items.append(item)

        if not _has_analyst_data(item):
            missing_data.append(ticker)

    items = sort_analyst_items(items, portfolio_set)
    portfolio_items = [item for item in items if item.get("in_portfolio")]
    watchlist_items = [item for item in items if not item.get("in_portfolio")]

    last_updated_values = [
        item.get("last_updated") for item in items if item.get("last_updated")
    ]
    last_updated = max(last_updated_values) if last_updated_values else _utc_now_iso()

    return {
        "items": items,
        "portfolio_items": portfolio_items,
        "watchlist_items": watchlist_items,
        "missing_data": missing_data,
        "last_updated": last_updated,
    }


def build_analyst_table(analyst_summary):
    rows = []
    for item in analyst_summary.get("items") or []:
        upside_pct = item.get("upside_pct")
        target_mean = item.get("target_mean")
        analyst_count = item.get("analyst_count")

        rows.append(
            {
                "Ticker": item.get("ticker", ""),
                "Konsensus": format_recommendation_label(
                    item.get("recommendation_key"),
                ),
                "Analytikere": analyst_count if analyst_count is not None else "—",
                "Kursmål": round(target_mean, 2) if target_mean is not None else "—",
                "Oppside %": upside_pct if upside_pct is not None else "—",
            }
        )

    return pd.DataFrame(rows)
