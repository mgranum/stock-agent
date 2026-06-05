def summarize_backtest_result(result):
    valid = result[result.get("error").isna()] if "error" in result.columns else result

    avg_strategy = round(valid["strategy_return_pct"].mean(), 2)
    avg_buy_hold = round(valid["buy_and_hold_return_pct"].mean(), 2)
    avg_diff = round(valid["difference_pct"].mean(), 2)
    avg_trades = round(valid["number_of_trades"].mean(), 2)

    winners = valid[valid["difference_pct"] > 0]
    losers = valid[valid["difference_pct"] <= 0]

    lines = []

    lines.append("BACKTEST-OPPSUMMERING")
    lines.append("")
    lines.append(f"Gjennomsnitt strategi: {avg_strategy}%")
    lines.append(f"Gjennomsnitt buy-and-hold: {avg_buy_hold}%")
    lines.append(f"Differanse: {avg_diff}%")
    lines.append(f"Snitt antall handler: {avg_trades}")
    lines.append(f"Slo buy-and-hold: {len(winners)} av {len(valid)}")
    lines.append("")

    lines.append("Best relativt til buy-and-hold:")
    for _, row in valid.sort_values("difference_pct", ascending=False).head(3).iterrows():
        lines.append(
            f"- {row['ticker']}: {row['difference_pct']}% "
            f"(strategi {row['strategy_return_pct']}%, B&H {row['buy_and_hold_return_pct']}%)"
        )

    lines.append("")
    lines.append("Svakest relativt til buy-and-hold:")
    for _, row in valid.sort_values("difference_pct", ascending=True).head(3).iterrows():
        lines.append(
            f"- {row['ticker']}: {row['difference_pct']}% "
            f"(strategi {row['strategy_return_pct']}%, B&H {row['buy_and_hold_return_pct']}%)"
        )

    return "\n".join(lines)