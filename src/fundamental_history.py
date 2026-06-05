from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import pandas as pd
import yfinance as yf


@dataclass
class FundamentalHistoryResult:
    ticker: str
    history: list[dict[str, Any]]
    fundamental_history_score: int
    fundamental_history_label: str
    fundamental_history_reasons: list[str]


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        if pd.isna(value):
            return None
        value = float(value)
        if math.isinf(value) or math.isnan(value):
            return None
        return value
    except Exception:
        return None


def _safe_div(numerator: Any, denominator: Any) -> float | None:
    numerator = _safe_float(numerator)
    denominator = _safe_float(denominator)

    if numerator is None or denominator is None or denominator == 0:
        return None

    return numerator / denominator


def _get_statement_row(df: pd.DataFrame, possible_names: list[str]) -> pd.Series | None:
    if df is None or df.empty:
        return None

    for name in possible_names:
        if name in df.index:
            return df.loc[name]

    return None


def _series_value(series: pd.Series | None, column: Any) -> float | None:
    if series is None:
        return None
    if column not in series.index:
        return None
    return _safe_float(series[column])


def _pct_change(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None:
        return None
    if previous == 0:
        return None
    return (current - previous) / abs(previous)


def fetch_fundamental_history(ticker: str, years: int = 5) -> list[dict[str, Any]]:
    """
    Henter historiske fundamentals fra yfinance.

    Returnerer én rad per år med:
    - revenue
    - revenue_growth
    - net_income
    - eps
    - eps_growth
    - gross_margin
    - operating_margin
    - net_margin
    - roe
    - debt_to_equity
    - free_cash_flow

    Merk:
    yfinance har varierende dekning, spesielt for nordiske aksjer.
    Manglende verdier returneres som None.
    """

    stock = yf.Ticker(ticker)

    income = stock.financials
    balance = stock.balance_sheet
    cashflow = stock.cashflow

    if income is None or income.empty:
        return []

    columns = list(income.columns)
    columns = sorted(columns, reverse=True)
    columns = columns[:years]

    revenue_row = _get_statement_row(
        income,
        ["Total Revenue", "Operating Revenue"],
    )
    gross_profit_row = _get_statement_row(
        income,
        ["Gross Profit"],
    )
    operating_income_row = _get_statement_row(
        income,
        ["Operating Income", "Operating Income or Loss"],
    )
    net_income_row = _get_statement_row(
        income,
        ["Net Income", "Net Income Common Stockholders"],
    )
    diluted_eps_row = _get_statement_row(
        income,
        ["Diluted EPS", "Basic EPS"],
    )

    total_equity_row = _get_statement_row(
        balance,
        [
            "Stockholders Equity",
            "Total Equity Gross Minority Interest",
            "Common Stock Equity",
        ],
    )
    total_debt_row = _get_statement_row(
        balance,
        ["Total Debt", "Net Debt"],
    )

    operating_cashflow_row = _get_statement_row(
        cashflow,
        ["Operating Cash Flow", "Total Cash From Operating Activities"],
    )
    capex_row = _get_statement_row(
        cashflow,
        ["Capital Expenditure", "Capital Expenditures"],
    )
    free_cashflow_row = _get_statement_row(
        cashflow,
        ["Free Cash Flow"],
    )

    rows: list[dict[str, Any]] = []

    for i, col in enumerate(columns):
        previous_col = columns[i + 1] if i + 1 < len(columns) else None

        revenue = _series_value(revenue_row, col)
        prev_revenue = _series_value(revenue_row, previous_col) if previous_col else None

        gross_profit = _series_value(gross_profit_row, col)
        operating_income = _series_value(operating_income_row, col)
        net_income = _series_value(net_income_row, col)

        eps = _series_value(diluted_eps_row, col)
        prev_eps = _series_value(diluted_eps_row, previous_col) if previous_col else None

        equity = _series_value(total_equity_row, col)
        debt = _series_value(total_debt_row, col)

        operating_cashflow = _series_value(operating_cashflow_row, col)
        capex = _series_value(capex_row, col)
        free_cashflow = _series_value(free_cashflow_row, col)

        if free_cashflow is None and operating_cashflow is not None and capex is not None:
            free_cashflow = operating_cashflow + capex

        year = col.year if hasattr(col, "year") else str(col)

        rows.append(
            {
                "year": year,
                "revenue": revenue,
                "revenue_growth": _pct_change(revenue, prev_revenue),
                "net_income": net_income,
                "eps": eps,
                "eps_growth": _pct_change(eps, prev_eps),
                "gross_margin": _safe_div(gross_profit, revenue),
                "operating_margin": _safe_div(operating_income, revenue),
                "net_margin": _safe_div(net_income, revenue),
                "roe": _safe_div(net_income, equity),
                "debt_to_equity": _safe_div(debt, equity),
                "free_cash_flow": free_cashflow,
            }
        )

    return rows


def score_fundamental_history(history: list[dict[str, Any]]) -> tuple[int, str, list[str]]:
    """
    Enkel fundamental trend-score 0–100.

    Vekt:
    - revenue growth
    - EPS growth
    - marginnivå / margintrend
    - ROE
    - gjeld
    - free cash flow
    """

    if not history:
        return 0, "INGEN HISTORIKK", ["Fant ikke historiske fundamentaldata."]

    score = 0
    reasons: list[str] = []

    recent = history[0]
    older = history[1:] if len(history) > 1 else []

    revenue_growth_values = [
        row["revenue_growth"]
        for row in history
        if row.get("revenue_growth") is not None
    ]

    eps_growth_values = [
        row["eps_growth"]
        for row in history
        if row.get("eps_growth") is not None
    ]

    net_margin_values = [
        row["net_margin"]
        for row in history
        if row.get("net_margin") is not None
    ]

    roe_values = [
        row["roe"]
        for row in history
        if row.get("roe") is not None
    ]

    fcf_values = [
        row["free_cash_flow"]
        for row in history
        if row.get("free_cash_flow") is not None
    ]

    debt_to_equity = recent.get("debt_to_equity")

    # Revenue growth
    if revenue_growth_values:
        positive_years = sum(1 for x in revenue_growth_values if x > 0)
        avg_growth = sum(revenue_growth_values) / len(revenue_growth_values)

        if positive_years >= 3:
            score += 20
            reasons.append("Revenue growth har vært positiv i flere år.")
        elif positive_years >= 2:
            score += 12
            reasons.append("Revenue growth har vært positiv i noen år.")

        if avg_growth > 0.15:
            score += 10
            reasons.append("Gjennomsnittlig revenue growth er sterk.")
        elif avg_growth > 0.05:
            score += 5
            reasons.append("Gjennomsnittlig revenue growth er positiv.")

    # EPS growth
    if eps_growth_values:
        positive_eps_years = sum(1 for x in eps_growth_values if x > 0)
        avg_eps_growth = sum(eps_growth_values) / len(eps_growth_values)

        if positive_eps_years >= 3:
            score += 15
            reasons.append("EPS growth har vært positiv i flere år.")
        elif positive_eps_years >= 2:
            score += 8
            reasons.append("EPS growth har vært positiv i noen år.")

        if avg_eps_growth > 0.15:
            score += 10
            reasons.append("Gjennomsnittlig EPS growth er sterk.")
        elif avg_eps_growth > 0.05:
            score += 5
            reasons.append("Gjennomsnittlig EPS growth er positiv.")

    # Margins
    if net_margin_values:
        latest_margin = net_margin_values[0]

        if latest_margin > 0.20:
            score += 15
            reasons.append("Net margin er høy.")
        elif latest_margin > 0.10:
            score += 10
            reasons.append("Net margin er solid.")
        elif latest_margin > 0.05:
            score += 5
            reasons.append("Net margin er positiv.")

        if len(net_margin_values) >= 3:
            if net_margin_values[0] > net_margin_values[-1]:
                score += 5
                reasons.append("Marginene er bedre enn tidligere i perioden.")

    # ROE
    if roe_values:
        latest_roe = roe_values[0]

        if latest_roe > 0.25:
            score += 15
            reasons.append("ROE er svært høy.")
        elif latest_roe > 0.15:
            score += 10
            reasons.append("ROE er god.")
        elif latest_roe > 0.08:
            score += 5
            reasons.append("ROE er positiv.")

    # Debt
    if debt_to_equity is not None:
        if debt_to_equity < 0.5:
            score += 10
            reasons.append("Gjeldsgraden er lav.")
        elif debt_to_equity < 1.5:
            score += 5
            reasons.append("Gjeldsgraden virker håndterbar.")
        elif debt_to_equity > 3:
            score -= 10
            reasons.append("Gjeldsgraden er høy.")

    # Free cash flow
    if fcf_values:
        positive_fcf_years = sum(1 for x in fcf_values if x > 0)

        if positive_fcf_years >= 3:
            score += 10
            reasons.append("Free cash flow har vært positiv i flere år.")
        elif positive_fcf_years >= 1:
            score += 5
            reasons.append("Free cash flow er positiv i siste periode(r).")

    score = max(0, min(100, round(score)))

    if score >= 80:
        label = "STERK FUNDAMENTAL UTVIKLING"
    elif score >= 60:
        label = "GOD FUNDAMENTAL UTVIKLING"
    elif score >= 40:
        label = "BLANDET FUNDAMENTAL UTVIKLING"
    elif score >= 20:
        label = "SVAK FUNDAMENTAL UTVIKLING"
    else:
        label = "SVÆRT SVAK / MANGLENDE FUNDAMENTAL HISTORIKK"

    if not reasons:
        reasons.append("For lite historikk til å gi tydelig fundamental vurdering.")

    return score, label, reasons


def analyze_fundamental_history(ticker: str, years: int = 5) -> dict[str, Any]:
    history = fetch_fundamental_history(ticker, years=years)
    score, label, reasons = score_fundamental_history(history)

    result = FundamentalHistoryResult(
        ticker=ticker,
        history=history,
        fundamental_history_score=score,
        fundamental_history_label=label,
        fundamental_history_reasons=reasons,
    )

    return {
        "ticker": result.ticker,
        "history": result.history,
        "fundamental_history_score": result.fundamental_history_score,
        "fundamental_history_label": result.fundamental_history_label,
        "fundamental_history_reasons": result.fundamental_history_reasons,
    }


def analyze_fundamental_history_for_watchlist(
    tickers: list[str],
    years: int = 5,
) -> list[dict[str, Any]]:
    results = []

    for ticker in tickers:
        try:
            result = analyze_fundamental_history(ticker, years=years)
            results.append(result)
        except Exception as e:
            results.append(
                {
                    "ticker": ticker,
                    "history": [],
                    "fundamental_history_score": 0,
                    "fundamental_history_label": "FEIL VED ANALYSE",
                    "fundamental_history_reasons": [str(e)],
                }
            )

    return sorted(
        results,
        key=lambda x: x.get("fundamental_history_score", 0),
        reverse=True,
    )


def print_fundamental_history_summary(result: dict[str, Any]) -> None:
    print("=" * 80)
    print(f"{result['ticker']} – {result['fundamental_history_label']}")
    print(f"Score: {result['fundamental_history_score']}/100")
    print()

    print("ÅRSHISTORIKK")
    for row in result["history"]:
        print(
            f"{row['year']}: "
            f"Revenue growth={_format_pct(row.get('revenue_growth'))}, "
            f"EPS growth={_format_pct(row.get('eps_growth'))}, "
            f"Net margin={_format_pct(row.get('net_margin'))}, "
            f"ROE={_format_pct(row.get('roe'))}, "
            f"D/E={_format_number(row.get('debt_to_equity'))}"
        )

    print()
    print("VURDERING")
    for reason in result["fundamental_history_reasons"]:
        print(f"- {reason}")


def _format_pct(value: Any) -> str:
    value = _safe_float(value)
    if value is None:
        return "N/A"
    return f"{value * 100:.1f}%"


def _format_number(value: Any) -> str:
    value = _safe_float(value)
    if value is None:
        return "N/A"
    return f"{value:.2f}"