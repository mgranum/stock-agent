import re

import pandas as pd

from src.config import load_json_config
from src.score_explainability import find_stock_analysis
from src.strategy_classification import STRATEGY_TYPES, _is_cyclical, add_strategy_types

DEFAULT_STRATEGY_PROFILES = {
    # Experimental trailing sensitivity test: slower SMA to reduce premature exits.
    "MOMENTUM": {
        "preferred_hold_days": 30,
        "preferred_stop_loss_pct": 0.08,
        "preferred_trailing_sma": "sma200",
        "style": "Aggressive trend following",
    },
    # Compounders need room for volatility and long holding periods.
    # Wider hard stops and slower trailing exits reduce premature stop-outs
    # on otherwise high-quality franchises.
    "QUALITY_COMPOUNDER": {
        "preferred_hold_days": 365,
        "preferred_stop_loss_pct": 0.20,
        "preferred_trailing_sma": "sma200",
        "style": "Long-term quality accumulation",
    },
    "COMPOUNDER": {
        "preferred_hold_days": 240,
        "preferred_stop_loss_pct": 0.18,
        "preferred_trailing_sma": "sma200",
        "style": "Quality with trend confirmation",
    },
    "CYCLICAL": {
        "preferred_hold_days": 45,
        "preferred_stop_loss_pct": 0.10,
        "preferred_trailing_sma": "sma100",
        "style": "Cyclical swing trading",
    },
    "WEAK/AVOID": {
        "preferred_hold_days": 0,
        "preferred_stop_loss_pct": 0.06,
        "preferred_trailing_sma": "sma20",
        "style": "Avoid or exit exposure",
    },
    "UNKNOWN": {
        "preferred_hold_days": 60,
        "preferred_stop_loss_pct": 0.12,
        "preferred_trailing_sma": "sma100",
        "style": "Default balanced handling",
    },
}


def load_strategy_profiles():
    return load_json_config(
        "strategy_profiles.json",
        DEFAULT_STRATEGY_PROFILES,
    )


def get_strategy_profile(strategy_type):
    profiles = load_strategy_profiles()
    return profiles.get(
        strategy_type,
        profiles.get("UNKNOWN", DEFAULT_STRATEGY_PROFILES["UNKNOWN"]),
    )


def _format_stop_pct(value):
    if value is None:
        return ""

    return f"{float(value) * 100:.0f}%"


def _format_stop_style(profile):
    trailing_sma = profile.get("preferred_trailing_sma", "")
    stop_pct = _format_stop_pct(profile.get("preferred_stop_loss_pct"))

    if trailing_sma and stop_pct:
        return f"{trailing_sma.upper()} trailing / {stop_pct} hard stop"

    return trailing_sma or stop_pct


def add_strategy_profile_columns(df):
    if df is None or df.empty:
        return df

    result = df.copy()

    if "strategy_type" not in result.columns:
        result = add_strategy_types(result)

    def profile_field(strategy_type, field):
        return get_strategy_profile(strategy_type).get(field)

    result["style"] = result["strategy_type"].map(
        lambda strategy_type: profile_field(strategy_type, "style")
    )
    result["preferred_hold_days"] = result["strategy_type"].map(
        lambda strategy_type: profile_field(strategy_type, "preferred_hold_days")
    )
    result["preferred_stop_loss_pct"] = result["strategy_type"].map(
        lambda strategy_type: _format_stop_pct(
            profile_field(strategy_type, "preferred_stop_loss_pct")
        )
    )

    return result


def strategy_profiles_overview():
    profiles = load_strategy_profiles()
    rows = []

    for strategy_type in STRATEGY_TYPES:
        profile = profiles.get(
            strategy_type,
            profiles.get("UNKNOWN", {}),
        )
        rows.append({
            "strategy_type": strategy_type,
            "style": profile.get("style", ""),
            "typical_hold_days": profile.get("preferred_hold_days"),
            "preferred_stop_style": _format_stop_style(profile),
        })

    return pd.DataFrame(rows)


# --- Investment style profiles (Strategy Profiles v2) ---

INVESTMENT_PROFILES = ("momentum", "quality", "value", "cyclical")

_PROFILE_LABELS = {
    "momentum": "Momentum",
    "quality": "Quality",
    "value": "Value",
    "cyclical": "Cyclical",
}

_PROFILE_TIEBREAK_PRIORITY = {
    "quality": 4,
    "momentum": 3,
    "value": 2,
    "cyclical": 1,
}

_CYCLICAL_SECTOR_KEYWORDS = (
    "shipping",
    "offshore",
    "energy",
    "oil",
    "gas",
    "metal",
    "mining",
    "steel",
    "fertilizer",
    "fertiliser",
    "gjødsel",
    "commodity",
    "commodities",
    "marine",
    "tanker",
    "råvare",
    "metall",
    "olje",
    "gass",
)

_CYCLICAL_TICKER_STEMS = (
    "FRO",
    "NAT",
    "STNG",
    "TNK",
    "DHT",
    "INSW",
)

_STRONG_TREND = "STERK OPPTREND"
_MODERATE_TREND = "MODERAT OPPTREND"
_MOMENTUM_RS_STRONG_THRESHOLD = 5.0
_MOMENTUM_HIGH_SCORE = 80
_MOMENTUM_STRONG_MOMENTUM_POINTS = 23
_MIN_VALUE_COMPONENTS = 2

_UNKNOWN_TICKER_MESSAGE = (
    "Jeg finner ikke {ticker} i aktiv analyse. "
    "Legg den til watchlist eller kjør screener med et univers som inkluderer den."
)


def _stock_dict(stock_analysis):
    if stock_analysis is None:
        return {}

    if isinstance(stock_analysis, pd.Series):
        return stock_analysis.to_dict()

    if isinstance(stock_analysis, dict):
        return stock_analysis

    return {}


def _safe_int(value, default=0):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return default

    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _relative_strength_20d(stock):
    return _safe_float(stock.get("relative_strength_20d")) or 0.0


def _momentum_rs_cap(relative_strength_20d):
    if relative_strength_20d <= 0:
        return 35
    if relative_strength_20d < 3:
        return 50
    if relative_strength_20d < _MOMENTUM_RS_STRONG_THRESHOLD:
        return 65
    return 100


def _score_momentum(stock):
    trend_points = _safe_int(stock.get("trend_points"))
    momentum_points = _safe_int(stock.get("momentum_points"))
    relative_strength_points = _safe_int(stock.get("relative_strength_points"))
    relative_strength_20d = _relative_strength_20d(stock)
    trend_regime = stock.get("trend_regime") or ""

    technical_raw = trend_points + momentum_points + relative_strength_points
    base = technical_raw / 80 * 100
    score = min(base, _momentum_rs_cap(relative_strength_20d))

    if trend_regime == _STRONG_TREND:
        if relative_strength_20d >= _MOMENTUM_RS_STRONG_THRESHOLD:
            score = min(100, score + 5)
    elif trend_regime == _MODERATE_TREND:
        score = min(score, 70)
    else:
        score = min(score, 40)

    if (
        relative_strength_20d < _MOMENTUM_RS_STRONG_THRESHOLD
        or momentum_points < _MOMENTUM_STRONG_MOMENTUM_POINTS
    ):
        score = min(score, _MOMENTUM_HIGH_SCORE)

    if relative_strength_20d < _MOMENTUM_RS_STRONG_THRESHOLD:
        if relative_strength_points == 0:
            trend_only_cap = 55 if trend_regime == _STRONG_TREND else 45
            score = min(score, trend_only_cap)
        elif relative_strength_20d < 3:
            score = min(score, 55)

    return min(100, max(0, round(score)))


def _score_quality(stock):
    fundamental_score = _safe_int(stock.get("fundamental_score"))
    fundamental_history_score = _safe_int(stock.get("fundamental_history_score"))
    score = round(fundamental_score * 0.35 + fundamental_history_score * 0.65)

    return_on_equity = _safe_float(stock.get("return_on_equity"))
    if return_on_equity is not None and return_on_equity > 0.15:
        score += 5

    profit_margin = _safe_float(stock.get("profit_margin"))
    if profit_margin is not None and profit_margin > 0.15:
        score += 5

    debt_to_equity = _safe_float(stock.get("debt_to_equity"))
    if debt_to_equity is not None:
        if debt_to_equity < 80:
            score += 5
        elif debt_to_equity > 150:
            score = max(0, score - 5)

    return min(100, max(0, score))


def _score_value(stock):
    score = 0
    components = 0

    price_to_book = _safe_float(stock.get("price_to_book"))
    if price_to_book is not None and price_to_book > 0:
        components += 1
        if price_to_book < 1.5:
            score += 30
        elif price_to_book < 3:
            score += 22
        elif price_to_book < 8:
            score += 12

    return_on_equity = _safe_float(stock.get("return_on_equity"))
    if return_on_equity is not None:
        components += 1
        if return_on_equity > 0.20:
            score += 25
        elif return_on_equity > 0.12:
            score += 15
        elif return_on_equity > 0:
            score += 5

    debt_to_equity = _safe_float(stock.get("debt_to_equity"))
    if debt_to_equity is not None:
        components += 1
        if debt_to_equity < 50:
            score += 25
        elif debt_to_equity < 100:
            score += 15
        elif debt_to_equity < 150:
            score += 5

    profit_margin = _safe_float(stock.get("profit_margin"))
    if profit_margin is None:
        profit_margin = _safe_float(stock.get("operating_margin"))
    if profit_margin is not None:
        components += 1
        if profit_margin > 0.20:
            score += 20
        elif profit_margin > 0.10:
            score += 12
        elif profit_margin > 0:
            score += 5

    trailing_pe = _safe_float(stock.get("trailing_pe"))
    forward_pe = _safe_float(stock.get("forward_pe"))
    pe_values = [
        value
        for value in (trailing_pe, forward_pe)
        if value is not None and value > 0
    ]
    if pe_values:
        components += 1
        pe = min(pe_values)
        if pe < 12:
            score += 15
        elif pe < 18:
            score += 10
        elif pe < 25:
            score += 5

    if components < _MIN_VALUE_COMPONENTS:
        return None

    return min(100, max(0, round(score)))


def _ticker_stem(ticker):
    ticker = str(ticker or "").upper()
    return ticker.split(".", 1)[0].split("-", 1)[0]


def _is_cyclical_ticker(ticker):
    if _is_cyclical(ticker):
        return True

    stem = _ticker_stem(ticker)
    return any(stem.startswith(prefix) for prefix in _CYCLICAL_TICKER_STEMS)


def _cyclical_keyword_matches(stock):
    sector = str(stock.get("sector") or "").lower()
    industry = str(stock.get("industry") or "").lower()
    text = f"{sector} {industry}".strip()

    if not text:
        return 0

    return sum(1 for keyword in _CYCLICAL_SECTOR_KEYWORDS if keyword in text)


def _score_cyclical(stock):
    ticker = stock.get("ticker", "")

    if _is_cyclical_ticker(ticker):
        return 90

    keyword_matches = _cyclical_keyword_matches(stock)
    if keyword_matches >= 2:
        return 92
    if keyword_matches == 1:
        return 78

    sector = stock.get("sector")
    industry = stock.get("industry")
    if sector or industry:
        return 10

    return 5


def _comparable_profiles(profiles):
    return {
        name: score
        for name, score in profiles.items()
        if score is not None
    }


def _primary_profile(profiles):
    comparable = _comparable_profiles(profiles)
    if not comparable:
        return "quality"

    return max(
        comparable,
        key=lambda name: (
            comparable[name],
            _PROFILE_TIEBREAK_PRIORITY[name],
        ),
    )


def _profile_explanation(stock, profiles, primary_profile):
    explanations = []

    if primary_profile == "quality":
        if _safe_int(stock.get("fundamental_score")) >= 70:
            explanations.append("sterk fundamental kvalitet")
        if _safe_int(stock.get("fundamental_history_score")) >= 80:
            explanations.append("sterk historisk utvikling")
        momentum_score = profiles.get("momentum")
        if momentum_score is not None and momentum_score < 75:
            explanations.append("moderat momentum")
    elif primary_profile == "momentum":
        if _safe_int(stock.get("trend_points")) >= 30:
            explanations.append("sterk opptrend")
        if _safe_float(stock.get("relative_strength_20d") or 0) > 0:
            explanations.append("høy relativ styrke")
        if _safe_int(stock.get("momentum_points")) >= 20:
            explanations.append("god momentum")
    elif primary_profile == "value":
        if _safe_float(stock.get("price_to_book")) is not None:
            explanations.append("interessant vurdering på P/B")
        if _safe_float(stock.get("return_on_equity")) is not None:
            explanations.append("solid avkastning på egenkapital")
        if _safe_float(stock.get("debt_to_equity")) is not None:
            explanations.append("akseptabel gjeldsprofil")
        pe_values = [
            value
            for value in (
                _safe_float(stock.get("trailing_pe")),
                _safe_float(stock.get("forward_pe")),
            )
            if value is not None and value > 0
        ]
        if pe_values:
            explanations.append("vurderingsmultipler tilgjengelig")
    elif primary_profile == "cyclical":
        if _is_cyclical_ticker(stock.get("ticker", "")):
            explanations.append("kjent syklisk ticker")
        sector = stock.get("sector")
        industry = stock.get("industry")
        if sector or industry:
            explanations.append(f"syklisk sektor/industri ({sector or industry})")
        else:
            explanations.append("syklisk profil basert på metadata")

    if not explanations:
        explanations.append("ingen tydelige profilmarkører tilgjengelig")

    return explanations


def build_strategy_profile(stock_analysis):
    stock = _stock_dict(stock_analysis)

    profiles = {
        "momentum": _score_momentum(stock),
        "quality": _score_quality(stock),
        "value": _score_value(stock),
        "cyclical": _score_cyclical(stock),
    }
    primary_profile = _primary_profile(profiles)

    return {
        "ticker": stock.get("ticker") or "Ukjent",
        "profiles": profiles,
        "primary_profile": primary_profile,
        "explanation": _profile_explanation(stock, profiles, primary_profile),
    }


def _format_profile_score(score):
    if score is None:
        return "ukjent"
    return str(score)


def format_strategy_profile(profile):
    profile = profile or {}
    ticker = profile.get("ticker") or "Ukjent"
    profiles = profile.get("profiles") or {}
    primary = profile.get("primary_profile") or "unknown"
    explanations = profile.get("explanation") or []

    lines = [
        ticker,
        "",
    ]

    for name in INVESTMENT_PROFILES:
        label = _PROFILE_LABELS[name]
        lines.append(f"{label}: {_format_profile_score(profiles.get(name))}")

    lines.extend([
        "",
        "Primær profil:",
        _PROFILE_LABELS.get(primary, str(primary)),
        "",
        "Forklaring:",
    ])
    lines.extend(f"- {line}" for line in explanations)

    return "\n".join(lines)


def is_strategy_profile_question(question):
    question = (question or "").lower()

    if any(
        phrase in question
        for phrase in [
            "strategi-profil",
            "strategiprofil",
            "strategi profil",
            "investeringsprofil",
            "investerings-profil",
        ]
    ):
        return True

    if "profilen til" in question or "profil til" in question:
        return True

    if "hvilken strategi" in question and "passer" in question:
        return True

    if "syklisk aksje" in question or "en syklisk" in question:
        return True

    return False


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


def extract_strategy_profile_ticker(question, context):
    question = (question or "").lower()

    for ticker in _tickers_for_matching(context):
        if ticker.lower() in question:
            return ticker

    for pattern in (
        r"strategi[- ]?profil(?:en)?(?:\s+(?:til|for))?\s+([a-z0-9.\-]+)",
        r"profil(?:en)?(?:\s+(?:til|for))?\s+([a-z0-9.\-]+)",
        r"(?:hvilken strategi(?:en)?\s+passer|passer)\s+([a-z0-9.\-]+)",
        r"\ber\s+([a-z0-9.\-]+)\s+en\s+syklisk",
    ):
        match = re.search(pattern, question)
        if match:
            return str(match.group(1)).strip().upper()

    return None


def format_strategy_profile_answer(context, question):
    ticker = extract_strategy_profile_ticker(question, context)
    if not ticker:
        return (
            "Spesifiser ticker, for eksempel:\n"
            "- Hvilken strategi passer BRK-B?\n"
            "- Hva er profilen til NVDA?\n"
            "- Er FRO en syklisk aksje?\n"
            "- Vis strategi-profil for MSFT"
        )

    stock = find_stock_analysis(
        ticker,
        context.get("watchlist_report"),
        context.get("portfolio_report"),
    )
    if stock is None:
        return _UNKNOWN_TICKER_MESSAGE.format(ticker=ticker)

    profile = build_strategy_profile(stock)
    question = (question or "").lower()

    if "syklisk" in question:
        cyclical_score = profile["profiles"]["cyclical"]
        comparable = _comparable_profiles(profile["profiles"])
        other_scores = [
            score
            for name, score in comparable.items()
            if name != "cyclical"
        ]
        is_cyclical = cyclical_score >= max(other_scores or [0])
        verdict = "Ja" if is_cyclical else "Nei"
        return (
            f"{ticker}\n\n"
            f"Syklisk profilscore: {cyclical_score}\n"
            f"Primær profil: {_PROFILE_LABELS[profile['primary_profile']]}\n\n"
            f"Svar: {verdict}, {ticker} "
            f"{'ser ut som en syklisk kandidat' if is_cyclical else 'ser ikke ut som en primært syklisk kandidat'}."
        )

    return format_strategy_profile(profile)
