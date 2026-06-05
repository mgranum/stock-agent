import pandas as pd


def build_portfolio_allocation(
    watchlist_report,
    max_buy_positions=5,
):
    if watchlist_report.empty:
        return {
            "buy_allocation": pd.DataFrame(),
            "hold_list": pd.DataFrame(),
            "avoid_list": pd.DataFrame(),
        }

    df = watchlist_report.copy()

    buy_candidates = df[
        df["anbefaling"] == "KJØP / ØK"
    ].copy()

    hold_candidates = df[
        df["anbefaling"] == "HOLD / OBSERVER"
    ].copy()

    avoid_candidates = df[
        df["anbefaling"] == "UNNGÅ / SELG"
    ].copy()

    buy_allocation = _build_buy_allocation(
        buy_candidates,
        max_positions=max_buy_positions,
    )

    hold_list = _build_hold_list(
        hold_candidates,
    )

    avoid_list = _build_avoid_list(
        avoid_candidates,
    )

    return {
        "buy_allocation": buy_allocation,
        "hold_list": hold_list,
        "avoid_list": avoid_list,
    }


def _build_buy_allocation(
    candidates,
    max_positions,
):
    if candidates.empty:
        return pd.DataFrame()

    candidates = candidates.sort_values(
        by=[
            "score",
            "fundamental_history_score",
            "relative_strength_20d",
        ],
        ascending=[False, False, False],
    ).head(max_positions)

    total_score = candidates["score"].sum()

    rows = []

    for _, row in candidates.iterrows():
        allocation_pct = (
            row["score"] / total_score
        ) * 100

        rows.append({
            "ticker": row["ticker"],
            "action": "KAN ØKES",
            "allocation_pct": round(allocation_pct, 1),
            "score": row["score"],
            "trend_regime": row["trend_regime"],
            "relative_strength_20d": row["relative_strength_20d"],
            "fundamental_score": row["fundamental_score"],
            "fundamental_history_score": row["fundamental_history_score"],
        })

    return pd.DataFrame(rows)


def _build_hold_list(candidates):
    if candidates.empty:
        return pd.DataFrame()

    rows = []

    candidates = candidates.sort_values(
        by=[
            "score",
            "fundamental_history_score",
            "fundamental_score",
        ],
        ascending=[False, False, False],
    )

    for _, row in candidates.iterrows():
        rows.append({
            "ticker": row["ticker"],
            "action": "BEHOLD / IKKE ØK",
            "score": row["score"],
            "trend_regime": row["trend_regime"],
            "relative_strength_20d": row["relative_strength_20d"],
            "fundamental_score": row["fundamental_score"],
            "fundamental_history_score": row["fundamental_history_score"],
        })

    return pd.DataFrame(rows)


def _build_avoid_list(candidates):
    if candidates.empty:
        return pd.DataFrame()

    rows = []

    candidates = candidates.sort_values(
        by=[
            "score",
        ],
        ascending=True,
    )

    for _, row in candidates.iterrows():
        rows.append({
            "ticker": row["ticker"],
            "action": "IKKE KJØP / VURDER SALG",
            "score": row["score"],
            "trend_regime": row["trend_regime"],
            "relative_strength_20d": row["relative_strength_20d"],
            "fundamental_score": row["fundamental_score"],
            "fundamental_history_score": row["fundamental_history_score"],
        })

    return pd.DataFrame(rows)