import pandas as pd

from src.signal_backtest import backtest_signal_model


EXIT_REASON_CATEGORIES = {
    "hard_stop_loss": "Hard stop-loss",
    "trailing_stop_trend": "Trailing stop + weak trend",
    "model_sell": "Model sell signal",
    "other": "Other",
    "unknown": "Unknown",
}


def _valid_backtest_rows(result_df):
    if result_df is None or result_df.empty:
        return pd.DataFrame()

    df = result_df.copy()

    if "error" in df.columns:
        df = df[df["error"].isna()]

    required = [
        "strategy_type",
        "strategy_return_pct",
        "buy_and_hold_return_pct",
        "difference_pct",
    ]
    if any(column not in df.columns for column in required):
        return pd.DataFrame()

    return df[df["strategy_type"].notna()]


def _primary_strategy_type_from_trades(trades_df, ticker=None):
    if trades_df is None or trades_df.empty:
        return None

    trades = trades_df.copy()
    if ticker is not None and "ticker" in trades.columns:
        trades = trades[trades["ticker"] == ticker]

    buys = trades[trades["action"] == "BUY"]
    if "strategy_type" in buys.columns:
        buys = buys[buys["strategy_type"].notna()]

    if buys.empty:
        return None

    if "date" in buys.columns:
        buys = buys.sort_values("date")

    return buys.iloc[0]["strategy_type"]


def attach_strategy_types(result_df, trades_df):
    if result_df is None or result_df.empty:
        return result_df

    enriched = result_df.copy()

    if "strategy_type" in enriched.columns and enriched["strategy_type"].notna().any():
        return enriched

    if trades_df is None or trades_df.empty:
        enriched["strategy_type"] = None
        return enriched

    ticker_column = "ticker" if "ticker" in enriched.columns else None
    if ticker_column is None:
        enriched["strategy_type"] = None
        return enriched

    enriched["strategy_type"] = enriched[ticker_column].map(
        lambda ticker: _primary_strategy_type_from_trades(trades_df, ticker)
    )
    return enriched


def collect_strategy_backtest_data(
    symbols,
    period="2y",
    initial_cash=10000,
    min_hold_days=60,
    stop_loss_pct=0.12,
    trailing_sma="sma100",
    min_buy_score=70,
    min_buy_relative_strength=0,
    require_risk_on=False,
):
    summaries = []
    trade_frames = []

    for symbol in symbols:
        try:
            summary, trades, _df = backtest_signal_model(
                symbol=symbol,
                period=period,
                initial_cash=initial_cash,
                min_hold_days=min_hold_days,
                stop_loss_pct=stop_loss_pct,
                trailing_sma=trailing_sma,
                min_buy_score=min_buy_score,
                min_buy_relative_strength=min_buy_relative_strength,
                require_risk_on=require_risk_on,
                strategy_specific=True,
            )
            summary["strategy_type"] = _primary_strategy_type_from_trades(trades)
            summaries.append(summary)

            if not trades.empty:
                symbol_trades = trades.copy()
                symbol_trades["ticker"] = symbol
                trade_frames.append(symbol_trades)

        except Exception as exc:
            summaries.append({
                "ticker": symbol,
                "error": str(exc),
            })

    result_df = pd.DataFrame(summaries)
    trades_df = (
        pd.concat(trade_frames, ignore_index=True)
        if trade_frames
        else pd.DataFrame()
    )
    return result_df, trades_df


def _classify_exit_reason(reason):
    if reason is None or pd.isna(reason):
        return "unknown"

    reason_text = str(reason)

    if "Hard stop" in reason_text:
        return "hard_stop_loss"

    if "Trailing stop" in reason_text:
        return "trailing_stop_trend"

    if "UNNGÅ" in reason_text or "SELG" in reason_text:
        return "model_sell"

    return "other"


def _round_metrics(df, columns):
    rounded = df.copy()
    for column in columns:
        if column in rounded.columns:
            rounded[column] = rounded[column].round(2)
    return rounded


def _group_by_strategy_type(valid):
    agg_map = {
        "avg_strategy_return_pct": ("strategy_return_pct", "mean"),
        "avg_buy_hold_return_pct": ("buy_and_hold_return_pct", "mean"),
        "avg_difference_pct": ("difference_pct", "mean"),
        "beat_buy_hold_count": (
            "difference_pct",
            lambda values: int((values > 0).sum()),
        ),
        "tested_symbols": ("ticker", "count"),
    }

    if "number_of_trades" in valid.columns:
        agg_map["avg_number_of_trades"] = ("number_of_trades", "mean")

    grouped = (
        valid.groupby("strategy_type", dropna=False)
        .agg(**agg_map)
        .reset_index()
        .sort_values("avg_difference_pct", ascending=False)
    )

    float_columns = [
        "avg_strategy_return_pct",
        "avg_buy_hold_return_pct",
        "avg_difference_pct",
        "avg_number_of_trades",
    ]
    return _round_metrics(grouped, float_columns)


def _performers_by_strategy_type(valid, per_strategy_limit=3):
    winner_rows = []
    loser_rows = []

    for strategy_type, group in valid.groupby("strategy_type", dropna=False):
        ranked = group.sort_values("difference_pct", ascending=False)

        for _, row in ranked.head(per_strategy_limit).iterrows():
            winner_rows.append({
                "strategy_type": strategy_type,
                "ticker": row["ticker"],
                "strategy_return_pct": round(row["strategy_return_pct"], 2),
                "buy_and_hold_return_pct": round(row["buy_and_hold_return_pct"], 2),
                "difference_pct": round(row["difference_pct"], 2),
                "number_of_trades": row.get("number_of_trades"),
            })

        for _, row in ranked.tail(per_strategy_limit).sort_values(
            "difference_pct",
            ascending=True,
        ).iterrows():
            loser_rows.append({
                "strategy_type": strategy_type,
                "ticker": row["ticker"],
                "strategy_return_pct": round(row["strategy_return_pct"], 2),
                "buy_and_hold_return_pct": round(row["buy_and_hold_return_pct"], 2),
                "difference_pct": round(row["difference_pct"], 2),
                "number_of_trades": row.get("number_of_trades"),
            })

    return (
        pd.DataFrame(winner_rows),
        pd.DataFrame(loser_rows),
    )


def _exit_reason_analysis(trades_df):
    if trades_df is None or trades_df.empty:
        return pd.DataFrame(), pd.DataFrame()

    sells = trades_df[trades_df["action"] == "SELL"].copy()
    if sells.empty or "reason" not in sells.columns:
        return pd.DataFrame(), pd.DataFrame()

    sells["exit_reason_category"] = sells["reason"].map(_classify_exit_reason)

    if "strategy_type" not in sells.columns:
        sells["strategy_type"] = None

    sells = sells[sells["strategy_type"].notna()]
    if sells.empty:
        return pd.DataFrame(), pd.DataFrame()

    grouped = (
        sells.groupby(["strategy_type", "exit_reason_category"], dropna=False)
        .agg(
            exit_count=("reason", "count"),
            avg_trade_gain_pct=("gain_pct", "mean"),
        )
        .reset_index()
    )

    totals = (
        sells.groupby("strategy_type", dropna=False)
        .size()
        .rename("total_exits")
        .reset_index()
    )

    grouped = grouped.merge(totals, on="strategy_type", how="left")
    grouped["exit_share_pct"] = (
        grouped["exit_count"] / grouped["total_exits"] * 100
    ).round(2)
    grouped["avg_trade_gain_pct"] = grouped["avg_trade_gain_pct"].round(2)
    grouped["exit_reason_label"] = grouped["exit_reason_category"].map(
        EXIT_REASON_CATEGORIES
    )

    overall = (
        sells.groupby("exit_reason_category", dropna=False)
        .agg(
            exit_count=("reason", "count"),
            avg_trade_gain_pct=("gain_pct", "mean"),
        )
        .reset_index()
        .sort_values("exit_count", ascending=False)
    )
    overall["exit_share_pct"] = (
        overall["exit_count"] / overall["exit_count"].sum() * 100
    ).round(2)
    overall["avg_trade_gain_pct"] = overall["avg_trade_gain_pct"].round(2)
    overall["exit_reason_label"] = overall["exit_reason_category"].map(
        EXIT_REASON_CATEGORIES
    )

    return grouped, overall


def analyze_strategy_backtest(result_df, trades_df=None, per_strategy_limit=3):
    enriched = attach_strategy_types(result_df, trades_df)
    valid = _valid_backtest_rows(enriched)

    empty_analysis = {
        "by_strategy_type": pd.DataFrame(),
        "top_winners_by_strategy_type": pd.DataFrame(),
        "worst_performers_by_strategy_type": pd.DataFrame(),
        "exit_reasons_by_strategy_type": pd.DataFrame(),
        "exit_reasons_overall": pd.DataFrame(),
        "tested_symbols": 0,
        "valid_symbols": 0,
    }

    if valid.empty:
        return empty_analysis

    by_strategy_type = _group_by_strategy_type(valid)
    top_winners, worst_performers = _performers_by_strategy_type(
        valid,
        per_strategy_limit=per_strategy_limit,
    )
    exit_by_strategy, exit_overall = _exit_reason_analysis(trades_df)

    return {
        "by_strategy_type": by_strategy_type,
        "top_winners_by_strategy_type": top_winners,
        "worst_performers_by_strategy_type": worst_performers,
        "exit_reasons_by_strategy_type": exit_by_strategy,
        "exit_reasons_overall": exit_overall,
        "tested_symbols": len(result_df) if result_df is not None else 0,
        "valid_symbols": len(valid),
    }


def summarize_strategy_backtest_analysis(analysis, per_strategy_limit=3):
    if analysis is None:
        return "Ingen strategi-backtestanalyse tilgjengelig."

    by_strategy = analysis.get("by_strategy_type")
    if by_strategy is None or by_strategy.empty:
        return "Ingen gyldige strategi-backtestresultater å analysere."

    lines = []
    lines.append("STRATEGI-BACKTESTANALYSE")
    lines.append("")
    lines.append(
        f"Testet symboler: {analysis.get('tested_symbols', 0)} | "
        f"Gyldige: {analysis.get('valid_symbols', 0)}"
    )
    lines.append("")

    lines.append("Per strategitype:")
    for _, row in by_strategy.iterrows():
        lines.append(
            f"- {row['strategy_type']}: "
            f"strategi {row['avg_strategy_return_pct']}%, "
            f"B&H {row['avg_buy_hold_return_pct']}%, "
            f"diff {row['avg_difference_pct']}%, "
            f"slo B&H {row['beat_buy_hold_count']}/{row['tested_symbols']}"
        )

    top_winners = analysis.get("top_winners_by_strategy_type")
    if top_winners is not None and not top_winners.empty:
        lines.append("")
        lines.append("Beste per strategitype:")
        for strategy_type in top_winners["strategy_type"].drop_duplicates():
            lines.append(f"- {strategy_type}:")
            subset = top_winners[
                top_winners["strategy_type"] == strategy_type
            ].head(per_strategy_limit)
            for _, row in subset.iterrows():
                lines.append(
                    f"  * {row['ticker']}: {row['difference_pct']}% "
                    f"(strategi {row['strategy_return_pct']}%, "
                    f"B&H {row['buy_and_hold_return_pct']}%)"
                )

    worst = analysis.get("worst_performers_by_strategy_type")
    if worst is not None and not worst.empty:
        lines.append("")
        lines.append("Svakeste per strategitype:")
        for strategy_type in worst["strategy_type"].drop_duplicates():
            lines.append(f"- {strategy_type}:")
            subset = worst[
                worst["strategy_type"] == strategy_type
            ].head(per_strategy_limit)
            for _, row in subset.iterrows():
                lines.append(
                    f"  * {row['ticker']}: {row['difference_pct']}% "
                    f"(strategi {row['strategy_return_pct']}%, "
                    f"B&H {row['buy_and_hold_return_pct']}%)"
                )

    exit_by_strategy = analysis.get("exit_reasons_by_strategy_type")
    if exit_by_strategy is not None and not exit_by_strategy.empty:
        lines.append("")
        lines.append("Exit-årsaker per strategitype:")
        for strategy_type in exit_by_strategy["strategy_type"].drop_duplicates():
            lines.append(f"- {strategy_type}:")
            subset = exit_by_strategy[
                exit_by_strategy["strategy_type"] == strategy_type
            ].sort_values("exit_count", ascending=False)
            for _, row in subset.iterrows():
                lines.append(
                    f"  * {row['exit_reason_label']}: "
                    f"{row['exit_count']} ({row['exit_share_pct']}%), "
                    f"snitt gevinst {row['avg_trade_gain_pct']}%"
                )

    exit_overall = analysis.get("exit_reasons_overall")
    if exit_overall is not None and not exit_overall.empty:
        lines.append("")
        lines.append("Exit-årsaker totalt:")
        for _, row in exit_overall.iterrows():
            lines.append(
                f"- {row['exit_reason_label']}: "
                f"{row['exit_count']} ({row['exit_share_pct']}%), "
                f"snitt gevinst {row['avg_trade_gain_pct']}%"
            )

    return "\n".join(lines)
