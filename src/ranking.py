import pandas as pd

from src.analysis import analyze_watchlist
from src.company_names import get_company_name
from src.strategy_profiles import add_strategy_profile_columns


def rank_watchlist(
    symbols,
    pause_seconds=1,
    min_score=None,
    only_buy_candidates=False,
):
    report = analyze_watchlist(
        symbols,
        pause_seconds=pause_seconds,
    )

    if "error" in report.columns:
        errors = report[report["error"].notna()]
        report = report[report["error"].isna()]

        if not errors.empty:
            print("Feil ved analyse:")
            print(errors[["ticker", "error"]])

    if report.empty:
        return report

    ranked = report.sort_values(
        by=[
            "score",
            "fundamental_history_score",
            "fundamental_score",
            "relative_strength_20d",
        ],
        ascending=[False, False, False, False],
    )

    if min_score is not None:
        ranked = ranked[ranked["score"] >= min_score]

    if only_buy_candidates:
        ranked = ranked[ranked["anbefaling"] == "KJØP / ØK"]

    return ranked.reset_index(drop=True)


def ranking_table(ranked_report):
    if ranked_report.empty:
        return pd.DataFrame()

    ranked_report = add_strategy_profile_columns(ranked_report)

    columns = [
        "ticker",
        "strategy_type",
        "style",
        "preferred_hold_days",
        "preferred_stop_loss_pct",
        "score",
        "anbefaling",
        "trend_regime",
        "relative_strength_20d",
        "technical_score",
        "fundamental_score",
        "fundamental_history_score",
        "kurs",
        "kursmål",
        "stop_loss",
        "trailing_stop_loss",
    ]

    existing_columns = [
        col for col in columns
        if col in ranked_report.columns
    ]

    table = ranked_report[existing_columns].copy()

    if "ticker" in table.columns and not table.empty:
        table.insert(
            1,
            "company_name",
            table["ticker"].map(get_company_name),
        )

    return table


def print_ranking(ranked_report, limit=10):
    table = ranking_table(ranked_report).head(limit)

    if table.empty:
        print("Ingen aksjer å vise.")
        return

    for i, row in table.iterrows():
        print(
            f"{i + 1}. {row['ticker']} | "
            f"score {row['score']} | "
            f"{row['anbefaling']} | "
            f"{row['trend_regime']} | "
            f"RS {row['relative_strength_20d']}% | "
            f"fund {row['fundamental_score']} | "
            f"hist {row['fundamental_history_score']}"
        )