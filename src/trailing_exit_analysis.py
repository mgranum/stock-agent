import pandas as pd

from src.data import get_daily_prices
from src.strategy_backtest_analysis import _classify_exit_reason

TRAILING_EXIT_CATEGORY = "trailing_stop_trend"


def _trailing_exit_trades(trades_df):
    if trades_df is None or trades_df.empty:
        return pd.DataFrame()

    sells = trades_df[trades_df["action"] == "SELL"].copy()
    if sells.empty or "reason" not in sells.columns:
        return pd.DataFrame()

    sells["exit_reason_category"] = sells["reason"].map(_classify_exit_reason)
    trailing = sells[
        sells["exit_reason_category"] == TRAILING_EXIT_CATEGORY
    ].copy()

    if "strategy_type" not in trailing.columns:
        trailing["strategy_type"] = None

    return trailing[trailing["strategy_type"].notna()]


def _load_price_series(ticker, period, price_data):
    if price_data is not None and ticker in price_data:
        return price_data[ticker]

    try:
        return get_daily_prices(ticker, period=period, use_cache=True)
    except Exception:
        return None


def _resolve_exit_index(price_df, exit_date):
    prices = price_df.sort_index()
    exit_ts = pd.Timestamp(exit_date)

    if exit_ts in prices.index:
        return prices.index.get_loc(exit_ts)

    prior = prices.index[prices.index <= exit_ts]
    if prior.empty:
        return None

    return prices.index.get_loc(prior[-1])


def _max_missed_upside_after_exit(exit_date, exit_price, price_df, horizon_days):
    if price_df is None or price_df.empty or pd.isna(exit_price):
        return None

    exit_index = _resolve_exit_index(price_df, exit_date)
    if exit_index is None:
        return None

    future = price_df.sort_index().iloc[
        exit_index + 1: exit_index + 1 + horizon_days
    ]
    if future.empty:
        return None

    peak_price = future["high"].max()
    return ((peak_price - exit_price) / exit_price) * 100


def _enrich_trailing_exits(trailing_df, price_data=None, period="2y"):
    rows = []

    for _, trade in trailing_df.iterrows():
        ticker = trade.get("ticker")
        exit_price = trade.get("price")
        price_df = _load_price_series(ticker, period, price_data)

        missed_20d = _max_missed_upside_after_exit(
            trade.get("date"),
            exit_price,
            price_df,
            20,
        )
        missed_60d = _max_missed_upside_after_exit(
            trade.get("date"),
            exit_price,
            price_df,
            60,
        )

        rows.append({
            **trade.to_dict(),
            "missed_upside_20d": missed_20d,
            "missed_upside_60d": missed_60d,
        })

    return pd.DataFrame(rows)


def _aggregate_trailing_metrics(trailing_df):
    if trailing_df.empty:
        return pd.DataFrame()

    grouped = (
        trailing_df.groupby("strategy_type", dropna=False)
        .agg(
            number_of_trades=("gain_pct", "count"),
            avg_gain_pct=("gain_pct", "mean"),
            median_gain_pct=("gain_pct", "median"),
            max_gain_pct=("gain_pct", "max"),
            win_rate=(
                "gain_pct",
                lambda values: round((values > 0).mean() * 100, 2),
            ),
            average_hold_days=("hold_days", "mean"),
            avg_missed_upside_20d=("missed_upside_20d", "mean"),
            avg_missed_upside_60d=("missed_upside_60d", "mean"),
        )
        .reset_index()
        .sort_values("number_of_trades", ascending=False)
    )

    float_columns = [
        "avg_gain_pct",
        "median_gain_pct",
        "max_gain_pct",
        "average_hold_days",
        "avg_missed_upside_20d",
        "avg_missed_upside_60d",
    ]
    for column in float_columns:
        if column in grouped.columns:
            grouped[column] = grouped[column].round(2)

    grouped["assessment"] = grouped.apply(_assess_trailing_sensitivity, axis=1)
    return grouped


def _assess_trailing_sensitivity(row):
    missed_20d = row.get("avg_missed_upside_20d")
    avg_gain = row.get("avg_gain_pct")

    if pd.isna(missed_20d):
        return "insufficient_post_exit_data"

    if missed_20d >= 5 and (pd.isna(avg_gain) or avg_gain >= 0):
        return "likely_cutting_winners_early"

    if missed_20d <= 0 and (pd.isna(avg_gain) or avg_gain <= 0):
        return "likely_protecting_capital"

    if missed_20d >= 5 and not pd.isna(avg_gain) and avg_gain < 0:
        return "mixed_exit_timing"

    if missed_20d < 5:
        return "trailing_exits_appear_balanced"

    return "review_manually"


def analyze_trailing_exits(trades_df, price_data=None, period="2y"):
    trailing = _trailing_exit_trades(trades_df)

    empty_analysis = {
        "by_strategy_type": pd.DataFrame(),
        "trailing_exits": pd.DataFrame(),
        "number_of_trailing_exits": 0,
    }

    if trailing.empty:
        return empty_analysis

    enriched = _enrich_trailing_exits(
        trailing,
        price_data=price_data,
        period=period,
    )
    by_strategy_type = _aggregate_trailing_metrics(enriched)

    return {
        "by_strategy_type": by_strategy_type,
        "trailing_exits": enriched,
        "number_of_trailing_exits": len(enriched),
    }


def summarize_trailing_exit_analysis(analysis):
    if analysis is None:
        return "Ingen trailing-exitanalyse tilgjengelig."

    by_strategy = analysis.get("by_strategy_type")
    if by_strategy is None or by_strategy.empty:
        return "Ingen trailing stop + trend-exits funnet."

    lines = []
    lines.append("TRAILING-EXITANALYSE")
    lines.append("")
    lines.append(
        f"Antall trailing-exits: {analysis.get('number_of_trailing_exits', 0)}"
    )
    lines.append("")

    lines.append("Per strategitype:")
    for _, row in by_strategy.iterrows():
        lines.append(f"- {row['strategy_type']}:")
        lines.append(
            f"  handler: {int(row['number_of_trades'])} | "
            f"snitt gevinst {row['avg_gain_pct']}% | "
            f"median {row['median_gain_pct']}% | "
            f"maks {row['max_gain_pct']}% | "
            f"win rate {row['win_rate']}% | "
            f"snitt hold {row['average_hold_days']} dager"
        )
        lines.append(
            f"  missed upside 20d: {row['avg_missed_upside_20d']}% | "
            f"60d: {row['avg_missed_upside_60d']}% | "
            f"vurdering: {row['assessment']}"
        )

    lines.append("")
    lines.append("Tolkning:")
    lines.append(
        "- Hoy missed upside etter exit tyder pa at trailing stop kan kutte vinnere for tidlig."
    )
    lines.append(
        "- Lav eller negativ missed upside med svak gevinst tyder pa at exit beskytter kapital."
    )

    return "\n".join(lines)
