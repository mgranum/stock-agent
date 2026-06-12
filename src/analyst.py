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

TARGET_MEAN_DELTA_PCT_THRESHOLD = 5.0
RECOMMENDATION_MEAN_DELTA_THRESHOLD = 0.25


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


def _normalize_recommendation_key(recommendation_key):
    if not recommendation_key:
        return None
    return str(recommendation_key).strip().lower()


def _apply_change_detection(data, previous_data):
    data = dict(data)
    previous_data = previous_data or {}

    prev_target = _safe_number(previous_data.get("target_mean"))
    prev_rec_mean = _safe_number(previous_data.get("recommendation_mean"))
    prev_rec_key = _normalize_recommendation_key(
        previous_data.get("recommendation_key"),
    )

    data["previous_target_mean"] = prev_target
    data["previous_recommendation_mean"] = prev_rec_mean
    if prev_rec_key is not None:
        data["previous_recommendation_key"] = prev_rec_key

    target_mean = _safe_number(data.get("target_mean"))
    rec_mean = _safe_number(data.get("recommendation_mean"))
    rec_key = _normalize_recommendation_key(data.get("recommendation_key"))

    data["target_mean_delta"] = None
    data["target_mean_delta_pct"] = None
    if target_mean is not None and prev_target is not None:
        data["target_mean_delta"] = round(target_mean - prev_target, 2)
        if prev_target != 0:
            data["target_mean_delta_pct"] = round(
                ((target_mean - prev_target) / prev_target) * 100,
                1,
            )

    data["recommendation_mean_delta"] = None
    if rec_mean is not None and prev_rec_mean is not None:
        data["recommendation_mean_delta"] = round(rec_mean - prev_rec_mean, 2)

    data["recommendation_changed"] = (
        prev_rec_key is not None
        and rec_key != prev_rec_key
    )

    return data


def _is_material_target_change(item):
    delta_pct = item.get("target_mean_delta_pct")
    if delta_pct is None:
        return False
    return delta_pct >= TARGET_MEAN_DELTA_PCT_THRESHOLD or (
        delta_pct <= -TARGET_MEAN_DELTA_PCT_THRESHOLD
    )


def _is_material_recommendation_mean_change(item):
    delta = item.get("recommendation_mean_delta")
    if delta is None:
        return False
    return abs(delta) >= RECOMMENDATION_MEAN_DELTA_THRESHOLD


def _collect_item_material_changes(item):
    changes = []
    ticker = item.get("ticker", "")

    delta_pct = item.get("target_mean_delta_pct")
    if _is_material_target_change(item):
        direction = "opp" if delta_pct > 0 else "ned"
        changes.append(
            {
                "ticker": ticker,
                "change_type": "target_mean",
                "Endring": f"Kursmål {direction} ({delta_pct:+.1f}%)",
                "Fra": item.get("previous_target_mean"),
                "Til": item.get("target_mean"),
            }
        )

    if _is_material_recommendation_mean_change(item):
        changes.append(
            {
                "ticker": ticker,
                "change_type": "recommendation_mean",
                "Endring": "Konsensus-score endret",
                "Fra": item.get("previous_recommendation_mean"),
                "Til": item.get("recommendation_mean"),
            }
        )

    if item.get("recommendation_changed"):
        changes.append(
            {
                "ticker": ticker,
                "change_type": "recommendation_key",
                "Endring": "Anbefaling endret",
                "Fra": format_recommendation_label(
                    item.get("previous_recommendation_key"),
                ),
                "Til": format_recommendation_label(item.get("recommendation_key")),
            }
        )

    return changes


def build_material_changes(items):
    changes = []
    for item in items or []:
        changes.extend(_collect_item_material_changes(item))
    return changes


def _format_change_value(value):
    if value is None:
        return "—"
    if isinstance(value, float):
        return round(value, 2)
    return value


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

    previous_data = None
    if cache_file.exists():
        with open(cache_file, "r", encoding="utf-8") as f:
            cached = json.load(f)

        if use_cache and cached.get("date") == today_iso:
            print(f"Bruker analyst-cache for {symbol}")
            return dict(cached["data"])

        previous_data = cached.get("data")

    data = _fetch_yfinance_analyst(symbol)
    data = _apply_change_detection(data, previous_data)
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

    material_changes = build_material_changes(items)

    return {
        "items": items,
        "portfolio_items": portfolio_items,
        "watchlist_items": watchlist_items,
        "missing_data": missing_data,
        "material_changes": material_changes,
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


def build_analyst_changes_table(analyst_summary):
    changes = analyst_summary.get("material_changes") or []
    if not changes:
        return pd.DataFrame()

    rows = []
    for change in changes:
        rows.append(
            {
                "Ticker": change.get("ticker", ""),
                "Endring": change.get("Endring", ""),
                "Fra": _format_change_value(change.get("Fra")),
                "Til": _format_change_value(change.get("Til")),
            }
        )

    return pd.DataFrame(rows)


def find_analyst_item(analyst_summary, ticker):
    normalized = str(ticker or "").strip().upper()
    for item in analyst_summary.get("items") or []:
        if str(item.get("ticker", "")).strip().upper() == normalized:
            return item
    return None


def analyst_tickers(analyst_summary):
    tickers = []
    for item in analyst_summary.get("items") or []:
        ticker = str(item.get("ticker", "")).strip().upper()
        if ticker and ticker not in tickers:
            tickers.append(ticker)
    return tickers


def _format_analyst_item_changes(item, material_changes=None):
    ticker = item.get("ticker")
    ticker_changes = [
        change
        for change in (material_changes or [])
        if change.get("ticker") == ticker
    ]
    if not ticker_changes:
        ticker_changes = _collect_item_material_changes(item)
    return ticker_changes


def format_analyst_item_answer(item, material_changes=None):
    ticker = item.get("ticker", "?")
    if not _has_analyst_data(item):
        return f"Analytikerkonsensus for {ticker}: Ingen data tilgjengelig."

    target_mean = item.get("target_mean")
    upside_pct = item.get("upside_pct")
    analyst_count = item.get("analyst_count")

    lines = [
        f"{ticker} – Analytikerkonsensus",
        "",
        f"Konsensus: {format_recommendation_label(item.get('recommendation_key'))}",
        f"Analytikere: {analyst_count if analyst_count is not None else '—'}",
        (
            f"Kursmål: {round(target_mean, 2) if target_mean is not None else '—'}"
        ),
        f"Oppside %: {upside_pct if upside_pct is not None else '—'}",
    ]

    ticker_changes = _format_analyst_item_changes(item, material_changes)
    if ticker_changes:
        lines.extend(["", "Endringer siden sist:"])
        for change in ticker_changes:
            fra = _format_change_value(change.get("Fra"))
            til = _format_change_value(change.get("Til"))
            lines.append(f"- {change.get('Endring')}: {fra} → {til}")

    lines.extend(["", DISCLAIMER])
    return "\n".join(lines)


def format_analyst_material_changes_answer(analyst_summary):
    changes = analyst_summary.get("material_changes") or []
    if not changes:
        return (
            "Analytikerendringer: Ingen materielle endringer siden sist.\n\n"
            f"{DISCLAIMER}"
        )

    lines = ["Analytikerendringer siden sist:", ""]
    for change in changes:
        fra = _format_change_value(change.get("Fra"))
        til = _format_change_value(change.get("Til"))
        lines.append(
            f"- {change.get('ticker')}: {change.get('Endring')} ({fra} → {til})"
        )

    lines.extend(["", DISCLAIMER])
    return "\n".join(lines)


def format_portfolio_analyst_upside_answer(analyst_summary, limit=5):
    items = [
        item
        for item in (analyst_summary.get("items") or [])
        if item.get("in_portfolio") and item.get("upside_pct") is not None
    ]

    if not items:
        return (
            "Portefølje – analytiker-oppside: Ingen data tilgjengelig.\n\n"
            f"{DISCLAIMER}"
        )

    ranked = sorted(
        items,
        key=lambda item: item.get("upside_pct") or float("-inf"),
        reverse=True,
    )

    lines = ["Porteføljeaksjer med størst analytiker-oppside:", ""]
    for item in ranked[:limit]:
        target_mean = item.get("target_mean")
        target_text = round(target_mean, 2) if target_mean is not None else "—"
        lines.append(
            f"- {item['ticker']}: {item['upside_pct']}% oppside "
            f"(kursmål {target_text}, "
            f"konsensus {format_recommendation_label(item.get('recommendation_key'))})"
        )

    lines.extend(["", DISCLAIMER])
    return "\n".join(lines)


def format_weakest_analyst_consensus_answer(analyst_summary, limit=5):
    items = [
        item
        for item in (analyst_summary.get("items") or [])
        if _has_analyst_data(item) and item.get("recommendation_mean") is not None
    ]

    if not items:
        return (
            "Svakeste analytikerkonsensus: Ingen data tilgjengelig.\n\n"
            f"{DISCLAIMER}"
        )

    ranked = sorted(
        items,
        key=lambda item: item.get("recommendation_mean") or float("-inf"),
        reverse=True,
    )

    lines = ["Svakeste analytikerkonsensus:", ""]
    for item in ranked[:limit]:
        analyst_count = item.get("analyst_count")
        count_text = analyst_count if analyst_count is not None else "—"
        lines.append(
            f"- {item['ticker']}: "
            f"{format_recommendation_label(item.get('recommendation_key'))} "
            f"(score {item['recommendation_mean']}, {count_text} analytikere)"
        )

    lines.extend(["", DISCLAIMER])
    return "\n".join(lines)
