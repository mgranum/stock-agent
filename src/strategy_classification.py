import pandas as pd

STRATEGY_TYPES = [
    "QUALITY_COMPOUNDER",
    "COMPOUNDER",
    "MOMENTUM",
    "CYCLICAL",
    "WEAK/AVOID",
    "UNKNOWN",
]

WEAK_TREND = "SVAK / NEGATIV TREND"
POSITIVE_TRENDS = ("MODERAT OPPTREND", "STERK OPPTREND")

# Display-only sector heuristics. These names are intentionally hardcoded
# because classification is metadata for the dashboard, not trading logic.
CYCLICAL_TICKERS = {
    # Energy
    "EQNR.OL",
    "AKRBP.OL",
    "VAR.OL",
    "ELK.OL",
    "BNOR.OL",
    # Metals / materials
    "NHY.OL",
    # Fertilizers / chemicals
    "YAR.OL",
    # Salmon / fish farming
    "MOWI.OL",
    "SALM.OL",
    "GSF.OL",
    "LSG.OL",
    # Shipping / offshore / supply
    "SUBC.OL",
    "OET.OL",
    "BWO.OL",
    "KIT.OL",
    # Industrial cyclicals
    "VOLV-B.ST",
    "VOLV-A.ST",
    "SAND.ST",
    "SKF-B.ST",
    "ABB.ST",
    "ATCO-A.ST",
    "ATCO-B.ST",
}

# Match common stems when exchanges/suffixes vary, e.g. VOLV-B.ST.
CYCLICAL_PREFIXES = (
    "EQNR",
    "AKRBP",
    "NHY",
    "YAR",
    "MOWI",
    "SALM",
    "SUBC",
    "VOLV",
    "VAR",
    "ELK",
    "GSF",
    "LSG",
    "SAND",
    "SKF",
)


def _recommendation(row):
    return row.get("anbefaling") or row.get("recommendation")


def _ticker_stem(ticker):
    ticker = str(ticker).upper()
    return ticker.split(".", 1)[0].split("-", 1)[0]


def _is_cyclical(ticker):
    ticker = str(ticker).upper()

    if ticker in CYCLICAL_TICKERS:
        return True

    stem = _ticker_stem(ticker)
    return any(stem.startswith(prefix) for prefix in CYCLICAL_PREFIXES)


def _is_weak_avoid(row):
    recommendation = _recommendation(row)
    score = row.get("score", 0) or 0

    return recommendation == "UNNGÅ / SELG" or score < 40


def _is_momentum(row):
    trend_regime = row.get("trend_regime")
    relative_strength_20d = row.get("relative_strength_20d", 0) or 0
    score = row.get("score", 0) or 0

    # Momentum trades need clear price leadership, not just a positive drift.
    return (
        trend_regime == "STERK OPPTREND"
        and relative_strength_20d > 3
        and score >= 70
    )


def _has_decent_momentum(row):
    trend_regime = row.get("trend_regime")
    relative_strength_20d = row.get("relative_strength_20d", 0) or 0

    # Compounder-with-trend: quality is working technically, but below
    # the stronger momentum threshold.
    return (
        trend_regime != WEAK_TREND
        and trend_regime in POSITIVE_TRENDS
        and relative_strength_20d > 0
    )


def _is_quality_compounder(row):
    fundamental_score = row.get("fundamental_score", 0) or 0
    fundamental_history_score = (
        row.get("fundamental_history_score", 0) or 0
    )
    recommendation = _recommendation(row)
    ticker = row.get("ticker", "")

    # Long-term quality franchises to hold through softer trend phases.
    # Think GOOGL / AMZN / META when fundamentals are strong but RS is muted.
    return (
        fundamental_score >= 75
        and fundamental_history_score >= 90
        and recommendation != "UNNGÅ / SELG"
        and not _is_cyclical(ticker)
        and not _is_momentum(row)
        and not _has_decent_momentum(row)
    )


def _is_compounder(row):
    fundamental_score = row.get("fundamental_score", 0) or 0
    fundamental_history_score = (
        row.get("fundamental_history_score", 0) or 0
    )
    ticker = row.get("ticker", "")

    # Quality plus confirmation: the business is strong and price action agrees.
    return (
        fundamental_score >= 80
        and fundamental_history_score >= 90
        and not _is_cyclical(ticker)
        and _has_decent_momentum(row)
    )


def classify_stock(row):
    # Mutually exclusive priority:
    # WEAK/AVOID -> CYCLICAL -> MOMENTUM -> QUALITY_COMPOUNDER -> COMPOUNDER -> UNKNOWN
    if _is_weak_avoid(row):
        return "WEAK/AVOID"

    if _is_cyclical(row.get("ticker", "")):
        return "CYCLICAL"

    if _is_momentum(row):
        return "MOMENTUM"

    if _is_quality_compounder(row):
        return "QUALITY_COMPOUNDER"

    if _is_compounder(row):
        return "COMPOUNDER"

    return "UNKNOWN"


def add_strategy_types(df):
    if df is None or df.empty:
        return df

    result = df.copy()
    result["strategy_type"] = result.apply(classify_stock, axis=1)
    return result


def strategy_type_counts(df):
    if df is None or df.empty:
        return {strategy_type: 0 for strategy_type in STRATEGY_TYPES}

    classified = add_strategy_types(df)
    counts = classified["strategy_type"].value_counts()

    return {
        strategy_type: int(counts.get(strategy_type, 0))
        for strategy_type in STRATEGY_TYPES
    }
