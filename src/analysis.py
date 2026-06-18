import time
import pandas as pd

from src.data import get_daily_prices
from src.indicators import add_indicators
from src.fundamentals import analyze_fundamentals, extract_value_fields
from src.fundamental_history import analyze_fundamental_history
from src.technicals import (
    get_benchmark_for_symbol,
    analyze_technicals,
)
from src.scoring import (
    calculate_stop_levels,
    combine_scores,
)


def analyze_stock(symbol):
    df = get_daily_prices(symbol)
    df = add_indicators(df)

    benchmark_symbol = get_benchmark_for_symbol(symbol)
    benchmark_df = get_daily_prices(benchmark_symbol)
    benchmark_df = add_indicators(benchmark_df)

    technical_result = analyze_technicals(
        df,
        benchmark_df,
        benchmark_symbol,
    )

    fundamental_result = analyze_fundamentals(symbol)
    fundamental_history_result = analyze_fundamental_history(symbol)

    scoring_result = combine_scores(
        technical_result,
        fundamental_result,
        fundamental_history_result,
    )

    stop_result = calculate_stop_levels(df)

    latest = df.iloc[-1]

    reasons = (
        technical_result["technical_reasons"]
        + scoring_result["score_reasons"]
    )

    result = {
        "ticker": symbol,
        "dato": df.index[-1].strftime("%Y-%m-%d"),
        "kurs": round(latest["close"], 2),

        "score": scoring_result["score"],
        "anbefaling": scoring_result["anbefaling"],

        "technical_score": technical_result["technical_score"],
        "trend_score": technical_result["trend_score"],
        "trend_regime": technical_result["trend_regime"],
        "trend_points": technical_result["trend_points"],
        "momentum_points": technical_result["momentum_points"],
        "volume_points": technical_result["volume_points"],
        "relative_strength_points": technical_result["relative_strength_points"],

        "fundamental_points": scoring_result["fundamental_points"],
        "fundamental_score": fundamental_result["fundamental_score"],
        "fundamental_label": fundamental_result["fundamental_label"],
        "fundamental_reasons": fundamental_result["fundamental_reasons"],

        "fundamental_history_points": scoring_result["fundamental_history_points"],
        "fundamental_history_score": fundamental_history_result[
            "fundamental_history_score"
        ],
        "fundamental_history_label": fundamental_history_result[
            "fundamental_history_label"
        ],
        "fundamental_history_reasons": fundamental_history_result[
            "fundamental_history_reasons"
        ],

        "benchmark": benchmark_symbol,
        "relative_strength_20d": technical_result["relative_strength_20d"],

        "tidshorisont": "2–6 uker",

        "begrunnelse": reasons,
    }

    result.update(extract_value_fields(fundamental_result))
    result.update(stop_result)

    return result, df


def analyze_watchlist(symbols, pause_seconds=1):
    results = []

    for i, symbol in enumerate(symbols, start=1):
        print(f"Analyserer {symbol} ({i}/{len(symbols)})...")

        try:
            result, df = analyze_stock(symbol)
            results.append(result)

        except Exception as e:
            results.append({
                "ticker": symbol,
                "error": str(e),
            })

        if i < len(symbols):
            time.sleep(pause_seconds)

    return pd.DataFrame(results)


def _report_field(row, *keys, default="—"):
    for key in keys:
        if key not in row:
            continue

        value = row[key]
        if value is None or (isinstance(value, float) and pd.isna(value)):
            continue

        return value

    return default


def _format_gain_pct(row):
    value = _report_field(row, "gain_pct", "unrealized_gain_pct", default=None)
    if value is None:
        return "—"

    try:
        return f"{float(value):g}"
    except (TypeError, ValueError):
        return "—"


def generate_text_report(watchlist_report, portfolio_report=None):
    lines = []

    lines.append("DAGENS RÅD")
    lines.append("")
    lines.append("Beste kandidater:")

    top = watchlist_report[
        (watchlist_report["score"] >= 55)
        & (watchlist_report["relative_strength_20d"] > 0)
        & (watchlist_report["anbefaling"] != "UNNGÅ / SELG")
    ].head(5)

    if top.empty:
        lines.append("- Ingen tydelige kjøpskandidater akkurat nå.")
    else:
        for _, row in top.iterrows():
            lines.append(
                f"- {row['ticker']}: {row['anbefaling']} "
                f"(score {row['score']}, {row['trend_regime']}, "
                f"fundamental score {row.get('fundamental_score', 'N/A')}, "
                f"historikk score {row.get('fundamental_history_score', 'N/A')}, "
                f"relativ styrke {row['relative_strength_20d']}%)"
            )

    if portfolio_report is not None and not portfolio_report.empty:
        lines.append("")
        lines.append("Portefølje:")

        for _, row in portfolio_report.iterrows():
            ticker = _report_field(row, "ticker")
            portefølje_råd = _report_field(row, "portefølje_råd")
            score = _report_field(row, "score")
            gain_pct = _format_gain_pct(row)
            lines.append(
                f"- {ticker}: {portefølje_råd} "
                f"(gevinst/tap {gain_pct}%, "
                f"score {score})"
            )

    return "\n".join(lines)