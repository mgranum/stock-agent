def summarize_rolling_walk_forward(rwf):
    required = {
        "fold",
        "test_avg_strategy_return_pct",
        "test_avg_buy_hold_return_pct",
        "test_avg_difference_pct",
        "test_beat_buy_hold_count",
        "tested_symbols",
    }
    if rwf is None or rwf.empty:
        return "Ingen walk-forward-resultater."
    if not required.issubset(rwf.columns):
        return "Walk-forward-resultatet mangler nødvendige kolonner."

    avg_diff = round(rwf["test_avg_difference_pct"].mean(), 2)
    avg_strategy = round(
        rwf["test_avg_strategy_return_pct"].mean(),
        2,
    )
    avg_buy_hold = round(
        rwf["test_avg_buy_hold_return_pct"].mean(),
        2,
    )
    positive_folds = int((rwf["test_avg_difference_pct"] > 0).sum())
    total_folds = len(rwf)
    beat_count = int(rwf["test_beat_buy_hold_count"].sum())
    comparison_count = int(rwf["tested_symbols"].sum())

    lines = [
        "KRONOLOGISK WALK-FORWARD",
        "",
        "Baseline: technical_only_v1 (frosset, ingen tuning per fold)",
        f"Folds: {total_folds}",
        f"Positiv relativ avkastning: {positive_folds} av {total_folds} folds",
        f"Slo buy-and-hold: {beat_count} av {comparison_count} ticker-folds",
        f"Gjennomsnitt strategi: {avg_strategy}%",
        f"Gjennomsnitt buy-and-hold: {avg_buy_hold}%",
        f"Gjennomsnitt differanse: {avg_diff}%",
    ]
    if rwf.get("test_portfolio_return_pct") is not None:
        portfolio_rows = rwf.dropna(
            subset=[
                "test_portfolio_return_pct",
                "test_portfolio_buy_hold_return_pct",
                "test_portfolio_difference_pct",
            ]
        )
        if not portfolio_rows.empty:
            lines.extend(
                [
                    "",
                    "Likt vektet portefølje:",
                    "- Strategi: "
                    f"{_average(portfolio_rows, 'test_portfolio_return_pct')}%",
                    "- Buy-and-hold: "
                    f"{_average(portfolio_rows, 'test_portfolio_buy_hold_return_pct')}%",
                    "- Differanse: "
                    f"{_average(portfolio_rows, 'test_portfolio_difference_pct')}%",
                    "- Maks drawdown strategi / buy-and-hold: "
                    f"{_average(portfolio_rows, 'test_portfolio_max_drawdown_pct')}% / "
                    f"{_average(portfolio_rows, 'test_portfolio_buy_hold_max_drawdown_pct')}%",
                    "- Sharpe strategi / buy-and-hold: "
                    f"{_average(portfolio_rows, 'test_portfolio_sharpe')} / "
                    f"{_average(portfolio_rows, 'test_portfolio_buy_hold_sharpe')}",
                ]
            )

    lines.extend(["", "Regioner – gjennomsnittlig differanse:"])
    for region, label in (
        ("usa", "USA"),
        ("norway", "Norge"),
        ("other_nordics", "Øvrige Norden"),
    ):
        value = _average(
            rwf,
            f"{region}_test_avg_difference_pct",
        )
        lines.append(f"- {label}: {value if value is not None else '–'}%")

    lines.extend(["", "Konklusjon:"])
    if avg_diff > 0 and positive_folds > total_folds / 2:
        lines.append(
            "- Baseline viser positiv relativ avkastning i et flertall av "
            "de kronologiske testvinduene."
        )
    else:
        lines.append(
            "- Baseline viser ikke stabil positiv relativ avkastning på "
            "tvers av de kronologiske testvinduene."
        )
    lines.append(
        "- Historiske folds er rolling tester, ikke den reserverte "
        "fremoverskuende OOS-perioden."
    )
    return "\n".join(lines)


def _average(frame, column):
    if column not in frame.columns:
        return None
    values = frame[column].dropna()
    if values.empty:
        return None
    return round(float(values.mean()), 2)
