from __future__ import annotations

import pandas as pd


def _numeric(value):
    if value is None:
        return None

    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _row_value(row, key):
    if isinstance(row, dict):
        return row.get(key)

    if hasattr(row, key):
        return getattr(row, key)

    try:
        return row[key]
    except (KeyError, TypeError, IndexError):
        return None


def _row_completeness(row):
    count = 0
    keys = row.index if hasattr(row, "index") else row.keys()
    for key in keys:
        value = _row_value(row, key)
        if value is None:
            continue
        try:
            if pd.isna(value):
                continue
        except TypeError:
            pass
        count += 1
    return count


def _primary_profile_score_from_row(row):
    primary_profile = _row_value(row, "primary_profile")
    if primary_profile:
        score = _numeric(_row_value(row, f"profile_score_{primary_profile}"))
        if score is not None:
            return score
    return -1


def _is_better_duplicate_row(candidate, incumbent):
    candidate_complete = _row_completeness(candidate)
    incumbent_complete = _row_completeness(incumbent)
    if candidate_complete != incumbent_complete:
        return candidate_complete > incumbent_complete

    candidate_profile_score = _primary_profile_score_from_row(candidate)
    incumbent_profile_score = _primary_profile_score_from_row(incumbent)
    if candidate_profile_score != incumbent_profile_score:
        return candidate_profile_score > incumbent_profile_score

    candidate_score = _numeric(_row_value(candidate, "score")) or -1
    incumbent_score = _numeric(_row_value(incumbent, "score")) or -1
    return candidate_score > incumbent_score


def deduplicate_screening_results(results):
    if results is None or results.empty:
        return results

    best_by_ticker = {}
    for _, row in results.iterrows():
        ticker = str(_row_value(row, "ticker") or "").strip().upper()
        if not ticker:
            continue

        existing = best_by_ticker.get(ticker)
        if existing is None or _is_better_duplicate_row(row, existing):
            best_by_ticker[ticker] = row

    if not best_by_ticker:
        return results.iloc[0:0].copy()

    return pd.DataFrame(list(best_by_ticker.values())).reset_index(drop=True)
