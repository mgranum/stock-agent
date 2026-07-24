from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

from src.screening_dedup import deduplicate_screening_results

DISCOVERY_REGIONS = ("USA", "NORDEN", "OBX")


def combine_discovery_candidates(
    screening_results,
    watchlist: Iterable[str] | None = None,
) -> pd.DataFrame:
    """Combine regional screens into one ranked, watchlist-independent universe."""
    if not isinstance(screening_results, dict):
        return pd.DataFrame()

    frames = []
    for region in DISCOVERY_REGIONS:
        results = screening_results.get(region)
        if not isinstance(results, pd.DataFrame) or results.empty:
            continue

        frame = results.copy()
        frame["source_universe"] = region
        frames.append(frame)

    if not frames:
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True, sort=False)
    combined = deduplicate_screening_results(combined)
    if combined is None or combined.empty:
        return pd.DataFrame()

    watchlist_symbols = {
        str(ticker).strip().upper()
        for ticker in (watchlist or [])
        if str(ticker).strip()
    }
    combined["in_watchlist"] = combined["ticker"].map(
        lambda ticker: str(ticker).strip().upper() in watchlist_symbols
    )

    sort_columns = ["in_watchlist"]
    ascending = [True]
    if "score" in combined.columns:
        sort_columns.append("score")
        ascending.append(False)
    combined = combined.sort_values(
        sort_columns,
        ascending=ascending,
        na_position="last",
        kind="stable",
    )

    return combined.reset_index(drop=True)
