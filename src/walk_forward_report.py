def summarize_rolling_walk_forward(rwf):
    if rwf.empty:
        return "Ingen walk-forward-resultater."

    lines = []

    lines.append("ROLLING WALK-FORWARD OPPSUMMERING")
    lines.append("")

    best = rwf.sort_values(
        by="test_avg_difference_pct",
        ascending=False,
    ).iloc[0]

    worst = rwf.sort_values(
        by="test_avg_difference_pct",
        ascending=True,
    ).iloc[0]

    avg_diff = round(rwf["test_avg_difference_pct"].mean(), 2)
    avg_strategy = round(rwf["test_avg_strategy_return_pct"].mean(), 2)
    avg_buy_hold = round(rwf["test_avg_buy_hold_return_pct"].mean(), 2)

    lines.append(f"Gjennomsnitt strategi: {avg_strategy}%")
    lines.append(f"Gjennomsnitt buy-and-hold: {avg_buy_hold}%")
    lines.append(f"Gjennomsnitt differanse: {avg_diff}%")
    lines.append("")

    lines.append("Beste test:")
    lines.append(
        f"- Train {best['train_period']} → test {best['test_period']}: "
        f"{best['test_avg_difference_pct']}% "
        f"({best['selected_config']})"
    )

    lines.append("")

    lines.append("Svakeste test:")
    lines.append(
        f"- Train {worst['train_period']} → test {worst['test_period']}: "
        f"{worst['test_avg_difference_pct']}% "
        f"({worst['selected_config']})"
    )

    lines.append("")

    lines.append("Konklusjon:")
    if avg_diff > 0:
        lines.append("- Modellen viser positiv out-of-sample edge.")
    else:
        lines.append("- Modellen viser foreløpig ikke stabil positiv out-of-sample edge.")

    if rwf["test_period"].astype(str).str.contains("6mo").any():
        six_month = rwf[rwf["test_period"] == "6mo"]
        if not six_month.empty and six_month["test_avg_difference_pct"].mean() > 0:
            lines.append("- Edge ser sterkest ut på kortere testvinduer.")

    return "\n".join(lines)