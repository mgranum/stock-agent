import re

import pandas as pd

_SCORE_LEVEL_REASONS = {
    "Sterk fundamental kvalitet",
    "Akseptabel fundamental kvalitet",
    "Svak eller uklar fundamental kvalitet",
    "Sterk historisk fundamental utvikling",
    "God historisk fundamental utvikling",
    "Blandet historisk fundamental utvikling",
    "Mangler historisk fundamental score",
    (
        "Sterke fundamentals, men teknisk setup er ikke sterkt nok "
        "for ny kjøpskandidat"
    ),
}

_TREND_REGIME_LABELS = {
    "STERK OPPTREND": "Sterk opptrend",
    "MODERAT OPPTREND": "Moderat opptrend",
    "SVAK / NEGATIV TREND": "Svak eller negativ trend",
}


def _safe_int(value, default=0):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return default

    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_reasons(value):
    if isinstance(value, list):
        return [str(reason) for reason in value if reason]

    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []

    return [str(value)]


def _stock_dict(stock_analysis):
    if stock_analysis is None:
        return {}

    if isinstance(stock_analysis, pd.Series):
        return stock_analysis.to_dict()

    if isinstance(stock_analysis, dict):
        return stock_analysis

    return {}


def _technical_reasons(stock):
    begrunnelse = _normalize_reasons(stock.get("begrunnelse"))
    technical = [
        reason
        for reason in begrunnelse
        if reason not in _SCORE_LEVEL_REASONS
    ]

    regime = stock.get("trend_regime")
    regime_label = _TREND_REGIME_LABELS.get(regime)
    if regime_label and regime_label not in technical:
        technical.append(regime_label)

    has_technical_context = bool(
        stock.get("ticker")
        or stock.get("technical_score") is not None
        or begrunnelse
        or regime
    )
    if not has_technical_context:
        return technical

    if _safe_int(stock.get("volume_points")) == 0:
        if not any("volum" in reason.lower() for reason in technical):
            technical.append("Ingen volumstøtte")

    if _safe_int(stock.get("relative_strength_points")) == 0:
        if not any(
            "benchmark" in reason.lower() or "relativ" in reason.lower()
            for reason in technical
        ):
            technical.append("Svak relativ styrke")

    return technical


def _collect_explanations(stock):
    explanations = []
    seen = set()

    for reason in (
        _technical_reasons(stock)
        + _normalize_reasons(stock.get("fundamental_reasons"))
        + _normalize_reasons(stock.get("fundamental_history_reasons"))
    ):
        if reason and reason not in seen:
            seen.add(reason)
            explanations.append(reason)

    return explanations


def build_score_explanation(stock_analysis):
    stock = _stock_dict(stock_analysis)

    trend_points = _safe_int(stock.get("trend_points"))
    momentum_points = _safe_int(stock.get("momentum_points"))
    volume_points = _safe_int(stock.get("volume_points"))
    relative_strength_points = _safe_int(stock.get("relative_strength_points"))
    technical_total = _safe_int(
        stock.get("technical_score"),
        trend_points + momentum_points + volume_points + relative_strength_points,
    )

    return {
        "ticker": stock.get("ticker") or "Ukjent",
        "score": _safe_int(stock.get("score")),
        "technical": {
            "total": technical_total,
            "trend_points": trend_points,
            "momentum_points": momentum_points,
            "volume_points": volume_points,
            "relative_strength_points": relative_strength_points,
        },
        "fundamental": {
            "snapshot_score": _safe_int(stock.get("fundamental_score")),
            "history_score": _safe_int(stock.get("fundamental_history_score")),
        },
        "explanations": _collect_explanations(stock),
    }


def format_score_explanation(explanation):
    explanation = explanation or {}
    technical = explanation.get("technical") or {}
    fundamental = explanation.get("fundamental") or {}
    explanations = explanation.get("explanations") or []

    lines = [
        str(explanation.get("ticker") or "Ukjent"),
        "",
        f"Total score: {explanation.get('score', 0)}",
        "",
        "Teknisk:",
        "",
        f"Trend: {technical.get('trend_points', 0)}",
        f"Momentum: {technical.get('momentum_points', 0)}",
        f"Volum: {technical.get('volume_points', 0)}",
        f"Relativ styrke: {technical.get('relative_strength_points', 0)}",
        "",
        "Fundamentalt:",
        "",
        f"Snapshot: {fundamental.get('snapshot_score', 0)}",
        f"Historikk: {fundamental.get('history_score', 0)}",
        "",
        "Viktigste forklaringer:",
        "",
    ]

    if explanations:
        lines.extend(f"- {reason}" for reason in explanations)
    else:
        lines.append("- Ingen detaljerte forklaringer tilgjengelig.")

    return "\n".join(lines)


def is_score_explanation_question(question):
    question = (question or "").lower()

    if any(
        phrase in question
        for phrase in [
            "score-forklaring",
            "score forklaring",
            "forklar scoren",
            "forklar score",
            "hvorfor scorer",
            "hvorfor får",
        ]
    ):
        return True

    if "satt sammen" in question:
        return True

    return "hvorfor" in question and "score" in question


def _tickers_for_matching(context):
    tickers = set()

    for source in (
        context.get("watchlist") or [],
        context.get("watchlist_report"),
        context.get("portfolio_report"),
    ):
        if isinstance(source, list):
            tickers.update(str(ticker).strip().upper() for ticker in source if ticker)
            continue

        if isinstance(source, pd.DataFrame) and not source.empty:
            tickers.update(
                source["ticker"].astype(str).str.strip().str.upper().tolist()
            )

    return sorted(tickers, key=len, reverse=True)


def extract_score_explanation_ticker(question, context):
    question = (question or "").lower()

    for ticker in _tickers_for_matching(context):
        if ticker.lower() in question:
            return ticker

    match = re.search(
        r"(?:score(?:n)?(?:\s+til|\s+for)?|scorer)\s+([a-z0-9.\-]+)",
        question,
    )
    if match:
        return str(match.group(1)).strip().upper()

    return None


def find_stock_analysis(ticker, watchlist_report, portfolio_report=None):
    if not ticker:
        return None

    ticker = str(ticker).strip().upper()

    for report in (watchlist_report, portfolio_report):
        if report is None or not isinstance(report, pd.DataFrame) or report.empty:
            continue

        match = report[report["ticker"].astype(str).str.upper() == ticker]
        if not match.empty:
            return match.iloc[0]

    return None
