import json
from datetime import date
from pathlib import Path

import yfinance as yf


def _safe_number(value):
    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def get_fundamentals(symbol, use_cache=True):
    today = date.today().isoformat()

    project_root = Path(__file__).resolve().parent.parent
    cache_dir = project_root / "cache"
    cache_dir.mkdir(exist_ok=True)

    cache_file = cache_dir / f"{symbol}_fundamentals.json"

    if use_cache and cache_file.exists():
        with open(cache_file, "r", encoding="utf-8") as f:
            cached = json.load(f)

        if cached.get("date") == today:
            print(f"Bruker fundamental-cache for {symbol}")
            return cached["data"]

    print(f"Henter fundamentals for {symbol}")

    ticker = yf.Ticker(symbol)
    info = ticker.info

    data = {
        "symbol": symbol,
        "market_cap": _safe_number(info.get("marketCap")),
        "trailing_pe": _safe_number(info.get("trailingPE")),
        "forward_pe": _safe_number(info.get("forwardPE")),
        "price_to_book": _safe_number(info.get("priceToBook")),
        "profit_margin": _safe_number(info.get("profitMargins")),
        "operating_margin": _safe_number(info.get("operatingMargins")),
        "revenue_growth": _safe_number(info.get("revenueGrowth")),
        "earnings_growth": _safe_number(info.get("earningsGrowth")),
        "debt_to_equity": _safe_number(info.get("debtToEquity")),
        "return_on_equity": _safe_number(info.get("returnOnEquity")),
        "dividend_yield": _safe_number(info.get("dividendYield")),
    }

    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(
            {
                "date": today,
                "symbol": symbol,
                "source": "yfinance",
                "data": data,
            },
            f,
            indent=2,
        )

    return data


def score_fundamentals(fundamentals):
    score = 0
    reasons = []

    revenue_growth = fundamentals.get("revenue_growth")
    earnings_growth = fundamentals.get("earnings_growth")
    profit_margin = fundamentals.get("profit_margin")
    operating_margin = fundamentals.get("operating_margin")
    return_on_equity = fundamentals.get("return_on_equity")
    debt_to_equity = fundamentals.get("debt_to_equity")
    trailing_pe = fundamentals.get("trailing_pe")
    forward_pe = fundamentals.get("forward_pe")
    price_to_book = fundamentals.get("price_to_book")

    if revenue_growth and revenue_growth > 0.10:
        score += 20
        reasons.append("Sterk omsetningsvekst")
    elif revenue_growth and revenue_growth > 0:
        score += 10
        reasons.append("Positiv omsetningsvekst")

    if earnings_growth and earnings_growth > 0.10:
        score += 20
        reasons.append("Sterk inntjeningsvekst")
    elif earnings_growth and earnings_growth > 0:
        score += 10
        reasons.append("Positiv inntjeningsvekst")

    if profit_margin and profit_margin > 0.20:
        score += 15
        reasons.append("Høy profit margin")
    elif profit_margin and profit_margin > 0.10:
        score += 10
        reasons.append("Akseptabel profit margin")

    if operating_margin and operating_margin > 0.20:
        score += 10
        reasons.append("Sterk operating margin")

    if return_on_equity and return_on_equity > 0.20:
        score += 15
        reasons.append("Høy avkastning på egenkapital")

    if debt_to_equity is not None:
        if debt_to_equity < 80:
            score += 10
            reasons.append("Moderat gjeldsgrad")
        elif debt_to_equity > 150:
            score -= 10
            reasons.append("Høy gjeldsgrad")

    if trailing_pe and trailing_pe > 35:
        score -= 10
        reasons.append("Høy trailing P/E")

    if forward_pe and forward_pe > 30:
        score -= 10
        reasons.append("Høy forward P/E")

    if price_to_book and price_to_book > 15:
        score -= 10
        reasons.append("Høy price/book")

    score = max(0, min(score, 100))

    if score >= 70:
        label = "STERK FUNDAMENTAL KVALITET"
    elif score >= 45:
        label = "AKSEPTABEL FUNDAMENTAL KVALITET"
    else:
        label = "SVAK / UKLAR FUNDAMENTAL KVALITET"

    return {
        "fundamental_score": score,
        "fundamental_label": label,
        "fundamental_reasons": reasons,
    }

def analyze_fundamentals(symbol):
    fundamentals = get_fundamentals(symbol)
    score = score_fundamentals(fundamentals)

    return {
        **fundamentals,
        **score,
    }