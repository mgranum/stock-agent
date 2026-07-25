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


def build_discovery_coverage(screening_results) -> dict:
    if not isinstance(screening_results, dict):
        return {"regions": {}, "candidates": 0, "snapshot": None}

    regions = {}
    for region in DISCOVERY_REGIONS:
        meta = (screening_results.get("meta") or {}).get(region) or {}
        regions[region] = {
            "universe_size": int(meta.get("universe_size") or 0),
            "coarse_passed": int(meta.get("coarse_passed") or 0),
            "selected_for_analysis": int(meta.get("selected_for_analysis") or 0),
            "coarse_rejected": int(meta.get("coarse_rejected") or 0),
            "analyzed": int(meta.get("analyzed") or 0),
            "failed": int(meta.get("failed") or 0),
            "passed_filters": int(meta.get("passed_filters") or 0),
            "rejected": list(meta.get("rejected") or []),
        }

    return {
        "regions": regions,
        "candidates": sum(
            int(region.get("passed_filters") or 0)
            for region in regions.values()
        ),
        "snapshot": screening_results.get("universe_snapshot"),
    }


def format_discovery_coverage(coverage) -> str:
    regions = (coverage or {}).get("regions") or {}
    parts = []
    for region in DISCOVERY_REGIONS:
        values = regions.get(region) or {}
        universe_size = int(values.get("universe_size") or 0)
        if not universe_size:
            continue
        analyzed = int(values.get("analyzed") or 0)
        selected = int(values.get("selected_for_analysis") or analyzed)
        parts.append(
            f"{region}: {universe_size} i universet → "
            f"{int(values.get('coarse_passed') or 0)} bestod grovfilter → "
            f"{selected} valgt for fullanalyse → "
            f"{analyzed} analysert → "
            f"{int(values.get('passed_filters') or 0)} kvalifiserte, "
            f"{int(values.get('failed') or 0)} analysefeil"
        )
    return " · ".join(parts)
