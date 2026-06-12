from collections import Counter

import pandas as pd

from src.data import get_daily_prices
from src.indicators import add_indicators
from src.model_backtest import load_snapshots
from src.orders import analyze_pending_orders
from src.portfolio import summarize_portfolio, valid_portfolio_rows
from src.regime import analyze_market_regime
from src.strategy_classification import add_strategy_types, strategy_type_counts
from src.strategy_profiles import (
    add_strategy_profile_columns,
    strategy_profiles_overview,
)
from src.research_ideas import summarize_research_ideas
from src.technicals import get_benchmark_for_symbol


def build_dashboard(
    watchlist_report,
    portfolio_report,
    pending_orders,
    watchlist_symbols=None,
    research_ideas=None,
):
    return {
        "portfolio_summary": summarize_portfolio(portfolio_report),
        "portfolio_risk": build_portfolio_risk(portfolio_report),
        "weakening_positions": _weakening_positions(
            portfolio_report,
            watchlist_report,
        ),
        "strong_winners": _strong_winners(portfolio_report),
        "top_buy_candidates": _top_buy_candidates(watchlist_report),
        "risk_alerts": _risk_alerts(watchlist_report, portfolio_report),
        "pending_orders": analyze_pending_orders(
            pending_orders,
            watchlist_report,
        ),
        "market_summary": _market_summary(watchlist_report),
        "market_regime": build_market_regime_summary(
            watchlist_symbols or [],
            watchlist_report,
        ),
        "changes_since_last_snapshot": _changes_since_last_snapshot(
            watchlist_report,
        ),
        "strategy_type_counts": strategy_type_counts(watchlist_report),
        "strategy_profiles": strategy_profiles_overview(),
        "research_ideas": summarize_research_ideas(research_ideas),
    }


def build_market_regime_summary(watchlist_symbols, watchlist_report=None):
    unavailable = {
        "available": False,
        "regime_label": "UNKNOWN",
        "benchmark_symbol": None,
        "benchmark_price": None,
        "sma20": None,
        "sma50": None,
        "sma100": None,
        "reasons": [],
        "interpretation": "Markedsregime utilgjengelig.",
        "watchlist_kpis": _watchlist_regime_kpis(watchlist_report),
        "message": "Markedsregime utilgjengelig.",
    }

    if not watchlist_symbols:
        return unavailable

    benchmark_symbol = _benchmark_for_watchlist(watchlist_symbols)

    try:
        benchmark_df = get_daily_prices(benchmark_symbol)
        benchmark_df = add_indicators(benchmark_df)
    except (ValueError, KeyError):
        return {
            **unavailable,
            "benchmark_symbol": benchmark_symbol,
            "message": (
                f"Kunne ikke hente benchmark-data for {benchmark_symbol}."
            ),
        }

    if len(benchmark_df) < 100:
        latest = benchmark_df.iloc[-1]
        return {
            **unavailable,
            "benchmark_symbol": benchmark_symbol,
            "benchmark_price": _round_metric(latest.get("close")),
            "sma20": _round_metric(latest.get("sma20")),
            "sma50": _round_metric(latest.get("sma50")),
            "sma100": _round_metric(latest.get("sma100")),
            "message": "For lite historikk til å beregne markedsregime.",
        }

    regime_result = analyze_market_regime(benchmark_df)
    latest = benchmark_df.iloc[-1]
    regime_label = _regime_display_label(regime_result)

    return {
        "available": True,
        "regime_label": regime_label,
        "benchmark_symbol": benchmark_symbol,
        "benchmark_price": _round_metric(latest["close"]),
        "sma20": _round_metric(latest["sma20"]),
        "sma50": _round_metric(latest["sma50"]),
        "sma100": _round_metric(latest["sma100"]),
        "reasons": regime_result["market_regime_reasons"],
        "interpretation": _regime_interpretation(regime_label),
        "watchlist_kpis": _watchlist_regime_kpis(watchlist_report),
        "message": None,
    }


def _benchmark_for_watchlist(symbols):
    benchmarks = [get_benchmark_for_symbol(symbol) for symbol in symbols]
    return Counter(benchmarks).most_common(1)[0][0]


def _regime_display_label(regime_result):
    score = regime_result["market_regime_score"]

    if regime_result["market_regime"] == "RISK_ON":
        return "RISK_ON"

    if score == 1:
        return "NEUTRAL"

    return "RISK_OFF"


def _regime_interpretation(regime_label):
    interpretations = {
        "RISK_ON": "Markedet støtter trendfølgende strategier",
        "RISK_OFF": "Defensiv posisjonering anbefales",
        "NEUTRAL": "Nøytralt marked – vær selektiv med nye posisjoner",
        "UNKNOWN": "Markedsregime utilgjengelig",
    }
    return interpretations.get(
        regime_label,
        "Markedsregime utilgjengelig",
    )


def _watchlist_regime_kpis(watchlist_report):
    if watchlist_report is None or watchlist_report.empty:
        return {
            "strong_uptrend_pct": 0,
            "weak_trend_pct": 0,
            "avg_relative_strength": 0,
        }

    total = len(watchlist_report)
    strong = int(
        (watchlist_report["trend_regime"] == "STERK OPPTREND").sum()
    )
    weak = int(
        (watchlist_report["trend_regime"] == "SVAK / NEGATIV TREND").sum()
    )
    avg_rs = float(watchlist_report["relative_strength_20d"].mean())

    return {
        "strong_uptrend_pct": round(strong / total * 100, 1),
        "weak_trend_pct": round(weak / total * 100, 1),
        "avg_relative_strength": round(avg_rs, 2),
    }


def _round_metric(value):
    if value is None or pd.isna(value):
        return None

    return round(float(value), 2)


def _top_buy_candidates(watchlist_report):
    if watchlist_report is None or watchlist_report.empty:
        return pd.DataFrame()

    df = watchlist_report[
        watchlist_report["anbefaling"] == "KJØP / ØK"
    ].copy()

    if df.empty:
        return pd.DataFrame()

    df = add_strategy_profile_columns(df)

    return df.sort_values(
        by=[
            "score",
            "relative_strength_20d",
            "fundamental_history_score",
        ],
        ascending=[False, False, False],
    )[
        [
            "ticker",
            "strategy_type",
            "style",
            "preferred_hold_days",
            "preferred_stop_loss_pct",
            "score",
            "trend_regime",
            "relative_strength_20d",
            "fundamental_score",
            "fundamental_history_score",
            "kurs",
            "stop_loss",
            "trailing_stop_loss",
        ]
    ].reset_index(drop=True)


def _risk_alerts(watchlist_report, portfolio_report):
    if portfolio_report is None or portfolio_report.empty:
        return pd.DataFrame()

    strategy_by_ticker = {}
    if watchlist_report is not None and not watchlist_report.empty:
        classified = add_strategy_types(watchlist_report)
        strategy_by_ticker = dict(
            zip(classified["ticker"], classified["strategy_type"])
        )

    rows = []
    df = valid_portfolio_rows(portfolio_report)

    for _, row in df.iterrows():
        strategy_type = strategy_by_ticker.get(
            row["ticker"],
            "UNKNOWN",
        )

        if row.get("trailing_stop_triggered") is True:
            rows.append({
                "ticker": row["ticker"],
                "strategy_type": strategy_type,
                "alert": "Trailing stop trigget",
                "severity": "HIGH",
                "details": row.get("begrunnelse", ""),
            })

        if row.get("trend_regime") == "SVAK / NEGATIV TREND":
            rows.append({
                "ticker": row["ticker"],
                "strategy_type": strategy_type,
                "alert": "Svak / negativ trend",
                "severity": "MEDIUM",
                "details": row.get("begrunnelse", ""),
            })

        if row.get("relative_strength_20d", 0) < -5:
            rows.append({
                "ticker": row["ticker"],
                "strategy_type": strategy_type,
                "alert": "Svak relativ styrke",
                "severity": "MEDIUM",
                "details": f"RS 20d: {row['relative_strength_20d']}%",
            })

    return pd.DataFrame(rows)


def _market_summary(watchlist_report):
    if watchlist_report is None or watchlist_report.empty:
        return {
            "total_symbols": 0,
            "buy_count": 0,
            "hold_count": 0,
            "avoid_count": 0,
        }

    return {
        "total_symbols": len(watchlist_report),
        "buy_count": int(
            (watchlist_report["anbefaling"] == "KJØP / ØK").sum()
        ),
        "hold_count": int(
            (watchlist_report["anbefaling"] == "HOLD / OBSERVER").sum()
        ),
        "avoid_count": int(
            (watchlist_report["anbefaling"] == "UNNGÅ / SELG").sum()
        ),
    }


# Portfolio risk and concentration analysis
_CONCENTRATION_TOP1_ELEVATED_PCT = 25.0
_CONCENTRATION_TOP1_HIGH_PCT = 35.0
_CONCENTRATION_TOP3_ELEVATED_PCT = 60.0
_CONCENTRATION_TOP3_HIGH_PCT = 70.0
_CONCENTRATION_LARGE_POSITION_PCT = 20.0
_GEO_DOMINANT_PCT = 65.0
_GEO_DOMINANT_HIGH_PCT = 80.0

_GEO_BUCKET_ORDER = (
    ("USA", "USA"),
    ("OBX", "OBX / Norge"),
    ("NORDEN", "Øvrig Norden"),
)


def _market_bucket_for_ticker(ticker):
    ticker = str(ticker).upper()
    if ticker.endswith(".OL"):
        return "OBX", "OBX / Norge"
    if ticker.endswith((".ST", ".CO", ".HE")):
        return "NORDEN", "Øvrig Norden"
    return "USA", "USA"


def _empty_portfolio_risk():
    return {
        "positions": 0,
        "total_market_value": 0,
        "top_position_pct": 0,
        "top3_concentration_pct": 0,
        "top_positions": pd.DataFrame(),
        "allocations": pd.DataFrame(),
        "available": False,
        "concentration": {
            "top_position_pct": 0,
            "top3_concentration_pct": 0,
            "positions_over_20pct": 0,
            "largest_positions": pd.DataFrame(),
            "flags": [],
        },
        "diversification": {
            "hhi": 0,
            "effective_n": 0,
            "equal_weight_pct": 0,
            "max_deviation_from_equal_pct": 0,
        },
        "geographic_exposure": {
            "buckets": [],
            "dominant_market": None,
            "dominant_market_pct": 0,
            "flags": [],
        },
        "risk_level": {
            "level": None,
            "score": 0,
            "reasons": [],
            "drivers": [],
        },
    }


def _portfolio_risk(portfolio_report):
    if portfolio_report is None or portfolio_report.empty:
        return _empty_portfolio_risk()

    df = valid_portfolio_rows(portfolio_report)

    if df.empty:
        return _empty_portfolio_risk()

    total_market = df["market_value"].sum()
    alloc = df[["ticker", "market_value"]].copy()
    alloc = alloc.groupby("ticker", as_index=False).sum()
    alloc["allocation_pct"] = alloc["market_value"] / total_market * 100
    alloc = alloc.sort_values(
        by="allocation_pct",
        ascending=False,
    ).reset_index(drop=True)

    top_positions = alloc.head(5).copy()
    positions_count = len(alloc)

    top_position_pct = round(
        float(top_positions.iloc[0]["allocation_pct"])
        if not top_positions.empty
        else 0,
        2,
    )
    top3_conc = round(
        float(top_positions.head(3)["allocation_pct"].sum())
        if not top_positions.empty
        else 0,
        2,
    )

    concentration = _build_concentration_metrics(
        alloc,
        top_position_pct,
        top3_conc,
    )
    diversification = _build_diversification_metrics(alloc, positions_count)
    geographic_exposure = _build_geographic_exposure(alloc, total_market)
    risk_level = _build_portfolio_risk_level(
        positions_count,
        top_position_pct,
        top3_conc,
        concentration["positions_over_20pct"],
        diversification["effective_n"],
        geographic_exposure["dominant_market"],
        geographic_exposure["dominant_market_pct"],
        top_positions,
    )

    return {
        "positions": positions_count,
        "total_market_value": round(total_market, 2),
        "top_position_pct": top_position_pct,
        "top3_concentration_pct": top3_conc,
        "top_positions": top_positions,
        "allocations": alloc,
        "available": True,
        "concentration": concentration,
        "diversification": diversification,
        "geographic_exposure": geographic_exposure,
        "risk_level": risk_level,
    }


def _build_concentration_metrics(alloc, top_position_pct, top3_conc):
    positions_over_20pct = int(
        (alloc["allocation_pct"] > _CONCENTRATION_LARGE_POSITION_PCT).sum()
    )
    largest_positions = alloc.head(5)[
        ["ticker", "market_value", "allocation_pct"]
    ].copy()

    flags = []
    if top_position_pct >= _CONCENTRATION_TOP1_HIGH_PCT:
        flags.append({
            "code": "TOP1_HIGH",
            "severity": "HIGH",
            "detail": f"Topp posisjon utgjør {top_position_pct}%.",
        })
    elif top_position_pct >= _CONCENTRATION_TOP1_ELEVATED_PCT:
        flags.append({
            "code": "TOP1_ELEVATED",
            "severity": "MEDIUM",
            "detail": f"Topp posisjon utgjør {top_position_pct}%.",
        })

    if top3_conc >= _CONCENTRATION_TOP3_HIGH_PCT:
        flags.append({
            "code": "TOP3_HIGH",
            "severity": "HIGH",
            "detail": f"Topp 3 utgjør {top3_conc}%.",
        })
    elif top3_conc >= _CONCENTRATION_TOP3_ELEVATED_PCT:
        flags.append({
            "code": "TOP3_ELEVATED",
            "severity": "MEDIUM",
            "detail": f"Topp 3 utgjør {top3_conc}%.",
        })

    if positions_over_20pct >= 3:
        flags.append({
            "code": "MANY_LARGE_POSITIONS",
            "severity": "MEDIUM",
            "detail": (
                f"{positions_over_20pct} posisjoner utgjør "
                f"mer enn {_CONCENTRATION_LARGE_POSITION_PCT:g} % hver."
            ),
        })

    return {
        "top_position_pct": top_position_pct,
        "top3_concentration_pct": top3_conc,
        "positions_over_20pct": positions_over_20pct,
        "largest_positions": largest_positions,
        "flags": flags,
    }


def _build_diversification_metrics(alloc, positions_count):
    if positions_count == 0:
        return {
            "hhi": 0,
            "effective_n": 0,
            "equal_weight_pct": 0,
            "max_deviation_from_equal_pct": 0,
        }

    weights = alloc["allocation_pct"] / 100
    hhi = round(float((weights ** 2).sum()), 4)
    effective_n = round(1 / hhi, 1) if hhi > 0 else 0
    equal_weight_pct = round(100 / positions_count, 2)
    max_deviation = round(
        float((alloc["allocation_pct"] - equal_weight_pct).abs().max()),
        2,
    )

    return {
        "hhi": hhi,
        "effective_n": effective_n,
        "equal_weight_pct": equal_weight_pct,
        "max_deviation_from_equal_pct": max_deviation,
    }


def _build_geographic_exposure(alloc, total_market):
    bucket_values = {market: 0.0 for market, _ in _GEO_BUCKET_ORDER}
    bucket_tickers = {market: [] for market, _ in _GEO_BUCKET_ORDER}
    bucket_counts = {market: 0 for market, _ in _GEO_BUCKET_ORDER}

    for _, row in alloc.iterrows():
        market, _ = _market_bucket_for_ticker(row["ticker"])
        bucket_values[market] += float(row["market_value"])
        bucket_tickers[market].append(row["ticker"])
        bucket_counts[market] += 1

    buckets = []
    for market, label in _GEO_BUCKET_ORDER:
        market_value = bucket_values[market]
        allocation_pct = round(
            market_value / total_market * 100,
            2,
        ) if total_market > 0 else 0
        buckets.append({
            "market": market,
            "label": label,
            "allocation_pct": allocation_pct,
            "market_value": round(market_value, 2),
            "position_count": bucket_counts[market],
            "tickers": bucket_tickers[market],
        })

    dominant = max(buckets, key=lambda item: item["allocation_pct"])
    dominant_market = dominant["market"] if dominant["allocation_pct"] > 0 else None
    dominant_market_pct = dominant["allocation_pct"]

    flags = []
    if dominant_market_pct >= _GEO_DOMINANT_HIGH_PCT:
        flags.append({
            "code": "GEO_DOMINANT_HIGH",
            "severity": "HIGH",
            "detail": (
                f"{dominant['label']} utgjør {dominant_market_pct} % "
                "av porteføljen."
            ),
        })
    elif dominant_market_pct >= _GEO_DOMINANT_PCT:
        flags.append({
            "code": "GEO_DOMINANT",
            "severity": "MEDIUM",
            "detail": (
                f"{dominant['label']} utgjør {dominant_market_pct} % "
                "av porteføljen."
            ),
        })

    return {
        "buckets": buckets,
        "dominant_market": dominant_market,
        "dominant_market_pct": dominant_market_pct,
        "flags": flags,
    }


def _build_portfolio_risk_level(
    positions_count,
    top_position_pct,
    top3_conc,
    positions_over_20pct,
    effective_n,
    dominant_market,
    dominant_market_pct,
    top_positions,
):
    if positions_count == 0:
        return {
            "level": None,
            "score": 0,
            "reasons": [],
            "drivers": [],
        }

    score = 0
    drivers = []

    if positions_count == 1:
        drivers.append("SINGLE_POSITION")
        return {
            "level": "HØY",
            "score": 3,
            "reasons": [
                "Porteføljen består av én enkelt posisjon.",
            ],
            "drivers": drivers,
        }

    if top_position_pct >= _CONCENTRATION_TOP1_HIGH_PCT:
        score += 2
        drivers.append("TOP1_HIGH")
    elif top_position_pct >= _CONCENTRATION_TOP1_ELEVATED_PCT:
        score += 1
        drivers.append("TOP1_ELEVATED")

    if top3_conc >= _CONCENTRATION_TOP3_HIGH_PCT:
        score += 2
        drivers.append("TOP3_HIGH")
    elif top3_conc >= _CONCENTRATION_TOP3_ELEVATED_PCT:
        score += 1
        drivers.append("TOP3_ELEVATED")

    if effective_n < 3:
        score += 2
        drivers.append("LOW_EFFECTIVE_N")
    elif effective_n < 5:
        score += 1
        drivers.append("MODERATE_EFFECTIVE_N")

    if dominant_market_pct >= _GEO_DOMINANT_HIGH_PCT:
        score += 2
        drivers.append("GEO_DOMINANT_HIGH")
    elif dominant_market_pct >= _GEO_DOMINANT_PCT:
        score += 1
        drivers.append("GEO_DOMINANT")

    if positions_over_20pct >= 3:
        score += 1
        drivers.append("MANY_LARGE_POSITIONS")

    if score <= 1:
        level = "LAV"
    elif score <= 3:
        level = "MEDIUM"
    else:
        level = "HØY"

    reasons = _portfolio_risk_reasons(
        top_positions,
        top_position_pct,
        top3_conc,
        effective_n,
        dominant_market,
        dominant_market_pct,
    )

    return {
        "level": level,
        "score": score,
        "reasons": reasons,
        "drivers": drivers,
    }


def _portfolio_risk_reasons(
    top_positions,
    top_position_pct,
    top3_conc,
    effective_n,
    dominant_market,
    dominant_market_pct,
):
    reasons = []
    market_labels = dict(_GEO_BUCKET_ORDER)

    if not top_positions.empty:
        top_ticker = top_positions.iloc[0]["ticker"]
        if top_position_pct >= _CONCENTRATION_TOP1_ELEVATED_PCT:
            reasons.append(
                f"{top_ticker} utgjør {top_position_pct} % av porteføljen."
            )

    if top3_conc >= _CONCENTRATION_TOP3_ELEVATED_PCT:
        reasons.append(f"Topp 3 utgjør {top3_conc} % av porteføljen.")

    if effective_n < 5:
        reasons.append(
            f"Effektiv diversifisering er {effective_n} (lav spredning)."
        )

    if dominant_market and dominant_market_pct >= _GEO_DOMINANT_PCT:
        label = market_labels.get(dominant_market, dominant_market)
        reasons.append(
            f"{label} utgjør {dominant_market_pct} % av porteføljen."
        )

    return reasons[:3]


def build_portfolio_risk(portfolio_report):
    return _portfolio_risk(portfolio_report)


def _weakening_positions(portfolio_report, watchlist_report=None):
    if portfolio_report is None or portfolio_report.empty:
        return pd.DataFrame()

    df = valid_portfolio_rows(portfolio_report)

    if df.empty:
        return pd.DataFrame()

    filt = (
        (df["trend_regime"] == "SVAK / NEGATIV TREND")
        | (df["relative_strength_20d"] < 0)
    )

    res = df[filt].copy()
    if res.empty:
        return pd.DataFrame()

    strategy_by_ticker = {}
    if watchlist_report is not None and not watchlist_report.empty:
        classified = add_strategy_types(watchlist_report)
        strategy_by_ticker = dict(
            zip(classified["ticker"], classified["strategy_type"])
        )

    res["strategy_type"] = res["ticker"].map(
        lambda ticker: strategy_by_ticker.get(ticker, "UNKNOWN")
    )
    res = add_strategy_profile_columns(res)

    cols = [
        "ticker",
        "strategy_type",
        "style",
        "preferred_hold_days",
        "preferred_stop_loss_pct",
        "market_value",
        "unrealized_gain_pct",
        "trend_regime",
        "relative_strength_20d",
    ]
    present_cols = [c for c in cols if c in res.columns]
    res = res[present_cols].sort_values(
        by=["relative_strength_20d", "unrealized_gain_pct"],
        ascending=[True, True],
    ).reset_index(drop=True)

    return res


def _strong_winners(portfolio_report):
    if portfolio_report is None or portfolio_report.empty:
        return pd.DataFrame()

    df = valid_portfolio_rows(portfolio_report)

    if df.empty:
        return pd.DataFrame()

    filt = (df["unrealized_gain_pct"] > 15) & (
        df["trend_regime"] != "SVAK / NEGATIV TREND"
    )

    res = df[filt].copy()
    if res.empty:
        return pd.DataFrame()

    cols = ["ticker", "market_value", "unrealized_gain_pct", "trend_regime"]
    present_cols = [c for c in cols if c in res.columns]
    res = res[present_cols].sort_values(by=["unrealized_gain_pct"], ascending=[False]).reset_index(drop=True)

    return res


_SNAPSHOT_CHANGE_COLUMNS = [
    "ticker",
    "previous_score",
    "current_score",
    "score_change",
    "previous_recommendation",
    "current_recommendation",
]


def _sort_snapshot_changes(df):
    if df.empty:
        return df

    return df.sort_values(
        by="score_change",
        key=lambda s: s.abs(),
        ascending=False,
    )[_SNAPSHOT_CHANGE_COLUMNS].reset_index(drop=True)


def _changes_since_last_snapshot(watchlist_report):
    snapshots = load_snapshots()

    if snapshots.empty:
        return None

    latest_date = sorted(snapshots["date"].unique())[-1]
    previous = snapshots[snapshots["date"] == latest_date][
        ["ticker", "score", "anbefaling"]
    ].rename(
        columns={
            "score": "previous_score",
            "anbefaling": "previous_recommendation",
        }
    )

    empty_sections = {
        "recommendation_changed": pd.DataFrame(),
        "large_score_changes": pd.DataFrame(),
    }

    if watchlist_report is None or watchlist_report.empty:
        return empty_sections

    current = watchlist_report[["ticker", "score", "anbefaling"]].rename(
        columns={
            "score": "current_score",
            "anbefaling": "current_recommendation",
        }
    )

    merged = current.merge(previous, on="ticker", how="inner")
    if merged.empty:
        return empty_sections

    merged["score_change"] = (
        merged["current_score"] - merged["previous_score"]
    )

    recommendation_changed = merged[
        merged["previous_recommendation"]
        != merged["current_recommendation"]
    ]

    large_score_changes = merged[
        (merged["previous_recommendation"] == merged["current_recommendation"])
        & (merged["score_change"].abs() >= 10)
    ]

    return {
        "recommendation_changed": _sort_snapshot_changes(
            recommendation_changed,
        ),
        "large_score_changes": _sort_snapshot_changes(
            large_score_changes,
        ),
    }
