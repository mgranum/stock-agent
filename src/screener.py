import time
import hashlib
from datetime import date

import pandas as pd

from src.analysis import analyze_stock, analyze_watchlist
from src.company_names import get_company_name
from src.config import load_discovery_config, load_json_config, load_watchlists
from src.data import get_daily_prices_batch
from src.ranking import rank_watchlist
from src.strategy_classification import add_strategy_types
from src.strategy_profiles import INVESTMENT_PROFILES, build_strategy_profile
from src.universe_sources import (
    load_official_nordics_universe,
    load_official_norway_universe,
    load_official_us_universe,
)


MIN_SUGGESTION_SCORE = 55
AVOID_RECOMMENDATION = "UNNGÅ / SELG"

SCREEN_RESULT_COLUMNS = [
    "ticker",
    "company_name",
    "score",
    "recommendation",
    "strategy_type",
    "trend_regime",
    "relative_strength_20d",
    "fundamental_score",
    "fundamental_history_score",
]

REJECTED_COLUMNS = [
    "ticker",
    "company_name",
    "score",
    "recommendation",
    "reason",
]

DIAGNOSTIC_KEYS = [
    "total_universe",
    "already_in_watchlists",
    "analyzed",
    "failed",
    "passed_filters",
    "filtered_low_score",
    "filtered_unnga_selg",
]

SCREEN_OUTPUT_COLUMNS = [
    "ticker",
    "in_watchlist",
    "score",
    "recommendation",
    "trend_regime",
    "relative_strength_20d",
    "fundamental_score",
    "fundamental_history_score",
    "primary_profile",
    "profile_score_momentum",
    "profile_score_quality",
    "profile_score_value",
    "profile_score_cyclical",
]

IN_WATCHLIST_YES = "Ja"
IN_WATCHLIST_NO = "Nei"


def _empty_screen_output():
    return pd.DataFrame(columns=SCREEN_OUTPUT_COLUMNS)


def _analysis_to_screen_row(result, watchlist_symbols=None):
    ticker = str(result["ticker"]).strip().upper()
    in_watchlist = IN_WATCHLIST_NO
    if watchlist_symbols is not None and ticker in watchlist_symbols:
        in_watchlist = IN_WATCHLIST_YES

    row = {
        "ticker": result["ticker"],
        "in_watchlist": in_watchlist,
        "score": result["score"],
        "recommendation": result["anbefaling"],
        "trend_regime": result["trend_regime"],
        "relative_strength_20d": result["relative_strength_20d"],
        "fundamental_score": result["fundamental_score"],
        "fundamental_history_score": result["fundamental_history_score"],
    }
    return _attach_strategy_profile_fields(result, row)


def _attach_strategy_profile_fields(analysis_result, row):
    profile = build_strategy_profile({**analysis_result, **row})
    profiles = profile.get("profiles") or {}

    row = dict(row)
    row["primary_profile"] = profile.get("primary_profile")
    for name in INVESTMENT_PROFILES:
        row[f"profile_score_{name}"] = profiles.get(name)

    return row


def load_screening_universe():
    universes = load_json_config("screening_universe.json", {})
    official_us = load_official_us_universe()
    if official_us:
        universes = dict(universes)
        universes["US_LARGE_CAP"] = official_us
    official_nordics = load_official_nordics_universe() or []
    official_norway = load_official_norway_universe() or []
    official_regions = official_nordics + official_norway
    if official_regions:
        universes = dict(universes)
        nordics = list(universes.get("NORDICS") or [])
        universes["NORDICS"] = sorted(set(nordics + official_regions))
    return universes


def _universe_symbols(universe_name):
    universes = load_screening_universe()

    if universe_name not in universes:
        known = ", ".join(sorted(universes)) or "(none configured)"
        raise ValueError(
            f"Unknown screening universe '{universe_name}'. "
            f"Available: {known}"
        )

    return list(universes[universe_name])


def _collect_existing_symbols(existing_watchlists):
    symbols = set()

    for list_name, tickers in existing_watchlists.items():
        if list_name == "Alle":
            continue
        symbols.update(ticker.strip().upper() for ticker in tickers)

    return symbols


def _watchlist_symbol_set(existing_watchlists=None):
    watchlists = existing_watchlists or load_watchlists()
    return _collect_existing_symbols(watchlists)


def screening_universe_options():
    return sorted(load_screening_universe())


def _sort_candidates(df):
    if df.empty:
        return df

    return df.sort_values(
        by=["score", "relative_strength_20d"],
        ascending=[False, False],
    ).reset_index(drop=True)


def _limit_results(df, max_results):
    if max_results is None or df.empty:
        return df

    return df.head(max_results).reset_index(drop=True)


def _format_screen_results(ranked_df):
    if ranked_df.empty:
        return pd.DataFrame(columns=SCREEN_RESULT_COLUMNS)

    result = add_strategy_types(ranked_df.copy())
    result["company_name"] = result["ticker"].map(get_company_name)
    result["recommendation"] = result["anbefaling"]

    return result[SCREEN_RESULT_COLUMNS].reset_index(drop=True)


def _empty_diagnostics(total_universe=0, already_in_watchlists=0):
    return {
        key: 0
        for key in DIAGNOSTIC_KEYS
    } | {
        "total_universe": total_universe,
        "already_in_watchlists": already_in_watchlists,
    }


def _empty_screening_result(total_universe=0, already_in_watchlists=0):
    return {
        "candidates": pd.DataFrame(columns=SCREEN_RESULT_COLUMNS),
        "diagnostics": _empty_diagnostics(
            total_universe=total_universe,
            already_in_watchlists=already_in_watchlists,
        ),
        "rejected": pd.DataFrame(columns=REJECTED_COLUMNS),
    }


def _rank_analyzed_report(report):
    if report.empty:
        return report

    return report.sort_values(
        by=[
            "score",
            "fundamental_history_score",
            "fundamental_score",
            "relative_strength_20d",
        ],
        ascending=[False, False, False, False],
    ).reset_index(drop=True)


def _filter_reason(row):
    recommendation = row.get("recommendation") or ""
    if recommendation == AVOID_RECOMMENDATION:
        return "UNNGÅ / SELG"

    score = row.get("score")
    if pd.isna(score) or score < MIN_SUGGESTION_SCORE:
        return "Lav score"

    return None


def _build_rejected_candidates(candidates, failed_report):
    rejected_rows = []

    for _, row in candidates.iterrows():
        reason = _filter_reason(row)
        if reason is None:
            continue

        rejected_rows.append({
            "ticker": row["ticker"],
            "company_name": row.get("company_name") or "",
            "score": row.get("score"),
            "recommendation": row.get("recommendation") or "",
            "reason": reason,
        })

    if failed_report is not None and not failed_report.empty:
        for _, row in failed_report.iterrows():
            rejected_rows.append({
                "ticker": row["ticker"],
                "company_name": get_company_name(row["ticker"]),
                "score": None,
                "recommendation": "",
                "reason": f"Analyse feilet: {row['error']}",
            })

    if not rejected_rows:
        return pd.DataFrame(columns=REJECTED_COLUMNS)

    rejected = pd.DataFrame(rejected_rows)
    return rejected.sort_values(
        by=["score"],
        ascending=[False],
        na_position="last",
    ).reset_index(drop=True)


def screen_universe(
    universe_name,
    max_results=None,
    max_symbols=None,
    pause_seconds=1,
):
    symbols = _universe_symbols(universe_name)

    if max_symbols is not None:
        symbols = symbols[:max_symbols]

    ranked = rank_watchlist(
        symbols,
        pause_seconds=pause_seconds,
    )
    results = _format_screen_results(ranked)
    return _limit_results(_sort_candidates(results), max_results)


def suggest_watchlist_additions(
    universe_name,
    existing_watchlists,
    max_results=None,
    max_symbols=None,
    pause_seconds=1,
):
    universe_symbols = _universe_symbols(universe_name)
    total_universe = len(universe_symbols)
    existing_symbols = _collect_existing_symbols(existing_watchlists)
    already_in_watchlists = sum(
        1
        for symbol in universe_symbols
        if symbol.strip().upper() in existing_symbols
    )

    symbols = [
        symbol
        for symbol in universe_symbols
        if symbol.strip().upper() not in existing_symbols
    ]

    if max_symbols is not None:
        symbols = symbols[:max_symbols]

    if not symbols:
        return _empty_screening_result(
            total_universe=total_universe,
            already_in_watchlists=already_in_watchlists,
        )

    report = analyze_watchlist(
        symbols,
        pause_seconds=pause_seconds,
    )

    failed_report = pd.DataFrame()
    if "error" in report.columns:
        failed_report = report[report["error"].notna()].copy()
        report = report[report["error"].isna()]

    analyzed = len(report)
    failed = len(failed_report)
    candidates = _format_screen_results(_rank_analyzed_report(report))

    if candidates.empty:
        diagnostics = _empty_diagnostics(
            total_universe=total_universe,
            already_in_watchlists=already_in_watchlists,
        )
        diagnostics.update({
            "analyzed": analyzed,
            "failed": failed,
        })
        return {
            "candidates": pd.DataFrame(columns=SCREEN_RESULT_COLUMNS),
            "diagnostics": diagnostics,
            "rejected": _build_rejected_candidates(
                candidates,
                failed_report,
            ),
        }

    reasons = candidates.apply(_filter_reason, axis=1)
    filtered = candidates[reasons.isna()]
    filtered_low_score = int((reasons == "Lav score").sum())
    filtered_unnga_selg = int((reasons == "UNNGÅ / SELG").sum())

    diagnostics = {
        "total_universe": total_universe,
        "already_in_watchlists": already_in_watchlists,
        "analyzed": analyzed,
        "failed": failed,
        "passed_filters": len(filtered),
        "filtered_low_score": filtered_low_score,
        "filtered_unnga_selg": filtered_unnga_selg,
    }

    return {
        "candidates": _limit_results(
            _sort_candidates(filtered),
            max_results,
        ),
        "diagnostics": diagnostics,
        "rejected": _build_rejected_candidates(
            candidates,
            failed_report,
        ),
    }


def screen_stocks(
    symbols,
    min_score=None,
    min_relative_strength=None,
    trend_regimes=None,
    limit=20,
    pause_seconds=1,
    watchlist_symbols=None,
    coarse_filter_config=None,
):
    if watchlist_symbols is None:
        watchlist_symbols = _watchlist_symbol_set()

    rows = []
    failed = 0
    rejected = []
    symbols_for_analysis = list(symbols)
    coarse_passed = [(symbol, 0.0) for symbol in symbols]
    if coarse_filter_config and coarse_filter_config.get("enabled", True):
        coarse_passed = []
        batch_prices, batch_errors = get_daily_prices_batch(
            symbols,
            period=coarse_filter_config.get("period", "6mo"),
        )
        for symbol in symbols:
            reason = _coarse_filter_reason(
                symbol,
                coarse_filter_config,
                prices=batch_prices.get(symbol),
                price_error=batch_errors.get(symbol),
            )
            if reason is None:
                coarse_passed.append(
                    (symbol, _average_traded_value(batch_prices[symbol]))
                )
            else:
                rejected.append({"ticker": symbol, "stage": "coarse_filter", "reason": reason})
        selected, not_selected = _select_for_full_analysis(
            coarse_passed,
            coarse_filter_config,
        )
        symbols_for_analysis = [symbol for symbol, _ in selected]
        for symbol, _ in not_selected:
            rejected.append({
                "ticker": symbol,
                "stage": "capacity_limit",
                "reason": (
                    "Bestod grovfilter, men ble ikke valgt i dagens "
                    "likviditets-/rotasjonsutvalg"
                ),
            })

    for i, symbol in enumerate(symbols_for_analysis, start=1):
        try:
            result, _ = analyze_stock(symbol)
            rows.append(
                _analysis_to_screen_row(result, watchlist_symbols)
            )
        except Exception as exc:
            failed += 1
            rejected.append({
                "ticker": symbol,
                "stage": "full_analysis",
                "reason": str(exc) or exc.__class__.__name__,
            })

        if pause_seconds and i < len(symbols_for_analysis):
            time.sleep(pause_seconds)

    if not rows:
        result = _empty_screen_output()
        result.attrs["diagnostics"] = {
            "requested": len(symbols),
            "coarse_passed": len(coarse_passed),
            "selected_for_analysis": len(symbols_for_analysis),
            "coarse_rejected": len(symbols) - len(coarse_passed),
            "analyzed": 0,
            "failed": failed,
            "passed_filters": 0,
            "rejected": rejected,
        }
        return result

    df = pd.DataFrame(rows)
    analyzed = len(df)

    if min_score is not None:
        df = df[df["score"] >= min_score]

    if min_relative_strength is not None:
        df = df[df["relative_strength_20d"] >= min_relative_strength]

    if trend_regimes is not None:
        allowed = (
            {trend_regimes}
            if isinstance(trend_regimes, str)
            else set(trend_regimes)
        )
        df = df[df["trend_regime"].isin(allowed)]

    df = df.sort_values(
        by=[
            "score",
            "fundamental_history_score",
            "fundamental_score",
            "relative_strength_20d",
        ],
        ascending=[False, False, False, False],
    )

    if limit is not None:
        df = df.head(limit)

    result = df[SCREEN_OUTPUT_COLUMNS].reset_index(drop=True)
    result.attrs["diagnostics"] = {
        "requested": len(symbols),
        "coarse_passed": len(coarse_passed),
        "selected_for_analysis": len(symbols_for_analysis),
        "coarse_rejected": len(symbols) - len(coarse_passed),
        "analyzed": analyzed,
        "failed": failed,
        "passed_filters": len(result),
        "rejected": rejected,
        "selection_policy": {
            "liquidity_top_slots": int(
                (coarse_filter_config or {}).get("liquidity_top_slots") or 0
            ),
            "mid_liquidity_slots": int(
                (coarse_filter_config or {}).get("mid_liquidity_slots") or 0
            ),
            "rotation_slots": max(
                0,
                len(symbols_for_analysis)
                - int((coarse_filter_config or {}).get("liquidity_top_slots") or 0)
                - int((coarse_filter_config or {}).get("mid_liquidity_slots") or 0),
            ),
        },
    }
    return result


def _coarse_filter_reason(
    symbol,
    config,
    prices=None,
    price_error=None,
    as_of_date=None,
):
    if price_error:
        return f"Yahoo-symbol mangler eller prisdata er utilgjengelig: {price_error}"
    if prices is None:
        return "Yahoo-symbol mangler eller prisdata er utilgjengelig"

    min_history_days = int(config.get("min_history_days", 60))
    if len(prices) < min_history_days:
        return f"For kort kurshistorikk ({len(prices)} < {min_history_days} dager)"

    if isinstance(prices.index, pd.DatetimeIndex) and not prices.index.empty:
        latest_date = prices.index.max().date()
        reference_date = as_of_date or date.today()
        price_age_days = (reference_date - latest_date).days
        max_price_age_days = int(config.get("max_price_age_days", 10))
        if price_age_days > max_price_age_days:
            return (
                "Siste kurs er for gammel "
                f"({price_age_days} > {max_price_age_days} dager); "
                "tickeren kan være stoppet, avnotert eller feil mappet"
            )

    recent = prices.tail(20)
    latest_price = pd.to_numeric(recent["close"], errors="coerce").dropna()
    if latest_price.empty:
        return "Mangler gyldig sluttkurs"
    min_price = float(config.get("min_price", 1.0))
    if float(latest_price.iloc[-1]) < min_price:
        return f"Kurs under minimum ({float(latest_price.iloc[-1]):.2f} < {min_price:.2f})"

    average_traded_value = _average_traded_value(recent)
    min_traded_value = float(config.get("min_average_traded_value_20d", 0))
    if pd.isna(average_traded_value) or average_traded_value < min_traded_value:
        measured = 0 if pd.isna(average_traded_value) else float(average_traded_value)
        return (
            "Lav omsatt verdi siste 20 dager "
            f"({measured:,.0f} < {min_traded_value:,.0f})"
        )

    return None


def _average_traded_value(prices):
    recent = prices.tail(20)
    close = pd.to_numeric(recent["close"], errors="coerce")
    volume = pd.to_numeric(recent["volume"], errors="coerce")
    value = (close * volume).dropna().mean()
    return 0.0 if pd.isna(value) else float(value)


def _select_for_full_analysis(coarse_passed, config, selection_date=None):
    ranked = sorted(coarse_passed, key=lambda item: item[1], reverse=True)
    limit = min(int(config.get("max_full_analysis") or len(ranked)), len(ranked))
    if limit >= len(ranked):
        return ranked, []

    top_slots = min(int(config.get("liquidity_top_slots") or limit), limit)
    mid_slots = min(
        int(config.get("mid_liquidity_slots") or 0),
        limit - top_slots,
    )
    selected = list(ranked[:top_slots])
    selected_symbols = {symbol for symbol, _ in selected}

    remaining = ranked[top_slots:]
    if mid_slots and remaining:
        start = len(remaining) // 4
        end = max(start + 1, (len(remaining) * 3) // 4)
        middle = remaining[start:end]
        if len(middle) <= mid_slots:
            mid_selected = middle
        else:
            step = len(middle) / mid_slots
            mid_selected = [middle[int(index * step)] for index in range(mid_slots)]
        selected.extend(mid_selected)
        selected_symbols.update(symbol for symbol, _ in mid_selected)

    rotation_slots = limit - len(selected)
    rotation_pool = [
        item for item in remaining if item[0] not in selected_symbols
    ]
    rotation_date = (selection_date or date.today()).isoformat()
    rotation_pool.sort(
        key=lambda item: hashlib.sha256(
            f"{rotation_date}:{item[0]}".encode("utf-8")
        ).hexdigest()
    )
    selected.extend(rotation_pool[:rotation_slots])
    selected_symbols.update(symbol for symbol, _ in rotation_pool[:rotation_slots])

    not_selected = [
        item for item in ranked if item[0] not in selected_symbols
    ]
    return selected, not_selected


SCREEN_PRESETS = {
    "Beste kandidater": {
        "min_score": 70,
    },
    "Sterk trend": {
        "trend_regimes": ["STERK OPPTREND"],
    },
    "Positiv relativ styrke": {
        "min_relative_strength": 0,
    },
    "Høy kvalitet + trend": {
        "min_score": 75,
        "min_relative_strength": 0,
    },
}


def get_preset_filters(preset_name):
    if preset_name not in SCREEN_PRESETS:
        known = ", ".join(sorted(SCREEN_PRESETS))
        raise ValueError(
            f"Unknown screening preset '{preset_name}'. "
            f"Available: {known}"
        )

    return dict(SCREEN_PRESETS[preset_name])


def screen_explore_universe(
    universe_name,
    preset=None,
    limit=20,
    pause_seconds=1,
    existing_watchlists=None,
):
    symbols = _universe_symbols(universe_name)
    watchlist_symbols = _watchlist_symbol_set(existing_watchlists)

    kwargs = {
        "limit": limit,
        "pause_seconds": pause_seconds,
        "watchlist_symbols": watchlist_symbols,
        "coarse_filter_config": (
            load_discovery_config().get("coarse_filter") or {}
        ),
    }

    if preset is not None:
        kwargs.update(get_preset_filters(preset))

    results = screen_stocks(symbols, **kwargs)
    diagnostics = dict(results.attrs.get("diagnostics") or {})
    diagnostics.update({
        "universe_name": universe_name,
        "universe_size": len(symbols),
        "preset": preset,
        "rejected": diagnostics.get("rejected") or [],
    })
    results.attrs["diagnostics"] = diagnostics
    return results


def screen_nordics(**kwargs):
    return screen_explore_universe("NORDICS", **kwargs)


def screen_us_large(**kwargs):
    return screen_explore_universe("US_LARGE_CAP", **kwargs)


def screen_obx(**kwargs):
    return screen_explore_universe("OBX", **kwargs)


screen_watchlist_universe = screen_explore_universe


def screen_quality_companies(symbols, pause_seconds=1):
    df = screen_stocks(
        symbols,
        limit=None,
        pause_seconds=pause_seconds,
    )
    if df.empty:
        return df

    return df[
        (df["score"] >= 55)
        & (df["fundamental_score"] >= 70)
        & (df["fundamental_history_score"] >= 70)
    ].reset_index(drop=True)


def screen_growth_with_trend(symbols, pause_seconds=1):
    df = screen_stocks(
        symbols,
        min_score=60,
        min_relative_strength=0,
        trend_regimes="STERK OPPTREND",
        pause_seconds=pause_seconds,
    )
    if df.empty:
        return df

    return df[df["fundamental_history_score"] >= 70].reset_index(drop=True)


def screen_buy_candidates(symbols, pause_seconds=1):
    df = screen_stocks(
        symbols,
        limit=None,
        pause_seconds=pause_seconds,
    )
    if df.empty:
        return df

    return df[df["recommendation"] == "KJØP / ØK"].reset_index(drop=True)


def screen_strong_fundamentals_weak_technical(symbols, pause_seconds=1):
    df = screen_stocks(
        symbols,
        limit=None,
        pause_seconds=pause_seconds,
    )
    if df.empty:
        return df

    return df[
        (df["fundamental_score"] >= 70)
        & (df["fundamental_history_score"] >= 70)
        & (df["recommendation"] != "KJØP / ØK")
    ].reset_index(drop=True)
