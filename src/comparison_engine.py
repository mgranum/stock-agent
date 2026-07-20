from __future__ import annotations

import re

import pandas as pd

from src.analyst import find_analyst_item, format_recommendation_label
from src.opportunity_advisor import build_opportunity_advisor
from src.score_explainability import find_stock_analysis
from src.strategy_profiles import _PROFILE_LABELS, build_strategy_profile

COMPARISON_MIN_TICKERS = 2
COMPARISON_MAX_TICKERS = 5
COMPARISON_TOP_LIST_DEFAULT = 3
COMPARISON_SCORE_TIE_GAP = 2

_TREND_RANK = {
    "STERK OPPTREND": 2,
    "MODERAT OPPTREND": 1,
    "SVAK / NEGATIV TREND": 0,
}

_TREND_DISPLAY = {
    "STERK OPPTREND": "Sterk opptrend",
    "MODERAT OPPTREND": "Moderat opptrend",
    "SVAK / NEGATIV TREND": "Svak eller negativ trend",
}

_COMPARISON_MARKERS = (
    "sammenlign",
    "versus",
    "best av",
    "bedre enn",
    "sterkest av",
    "hvilken av",
    "velge én",
    "velge en",
    "kjøpe én",
    "kjope en",
    "kjøpe en",
)

_PORTFOLIO_COMPARISON_MARKERS = (
    "bedre ut enn det jeg eier",
    "bedre ut enn det jeg har",
    "sterkere kandidater enn mine svakeste",
    "sterkere kandidater enn de svakeste",
    "mest interessante kjøpskandidat",
)

_SCREENING_REGIONS = {
    "obx": ("obx", "norske kandidater", "norske aksjer", "beste norske", "norsk"),
    "nordics": ("nordisk", "nordiske", "norden"),
    "usa": ("amerikansk", "amerikanske", " usa", "us "),
}

_STRATEGY_PROFILES = {
    "momentum": ("momentum", "momentum-kandidat", "momentum-kandidater"),
    "quality": ("quality", "kvalitetsaksj", "kvalitetskandidat"),
    "value": ("value", "verdiaksj", "value-aksj"),
    "cyclical": ("cyclical", "syklisk", "sykliske"),
}

_SCREENING_SNAPSHOT_KEYS = {
    "usa": "USA",
    "nordics": "NORDEN",
    "obx": "OBX",
}

_MISSING_TICKER_MESSAGE = (
    "Jeg finner ikke nok snapshot-data for {ticker}. Kjør Oppdater analyser."
)

_TICKER_STOPWORDS = frozenset({"AV", "VS", "OG", "ER", "EN"})

_ANALYST_RANK = {
    "strong_buy": 5,
    "buy": 4,
    "hold": 3,
    "sell": 2,
    "strong_sell": 1,
}

_EXPLANATION_MAX_ADVANTAGES = 3
_EXPLANATION_MAX_TRADEOFFS = 2
_EXPLANATION_MAX_WHY_NOT = 2

_ADVANTAGE_SPECS = (
    ("total_score", 1, "score", "Høyest totalscore ({winner}: {winner_value} vs {other}: {other_value})."),
    ("trend", 2, "trend_regime", "{winner} har sterkere trend ({winner_value} vs {other_value})."),
    ("relative_strength", 3, "relative_strength_20d", "Sterkere relativ styrke ({winner}: {winner_value} vs {other}: {other_value})."),
    ("fundamentals", 4, "fundamental_score", "Sterkere fundamentale tall ({winner}: {winner_value} vs {other}: {other_value})."),
    ("fundamental_history", 5, "fundamental_history_score", "Bedre fundamental historikk ({winner}: {winner_value} vs {other}: {other_value})."),
    ("profile_fit", 6, "primary_profile_score_display", "{winner} har sterkere {profile_label}-profil ({winner_value} vs {other_value})."),
)

_TRADEOFF_SPECS = (
    ("fundamentals", "fundamental_score", "Svakere fundamentale tall ({winner}: {winner_value} vs {best_other}: {other_value})."),
    ("fundamental_history", "fundamental_history_score", "Svakere fundamental historikk ({winner}: {winner_value} vs {best_other}: {other_value})."),
    ("relative_strength", "relative_strength_20d", "Svakere relativ styrke ({winner}: {winner_value} vs {best_other}: {other_value})."),
    ("trend", "trend_regime", "Trenden er ikke like sterk ({winner_value} vs {best_other}: {other_value})."),
    ("profile_fit", "primary_profile_score_display", "Svakere profilscore ({winner}: {winner_value} vs {best_other}: {other_value})."),
)

_CATEGORY_NARRATIVE = {
    "total_score": "totalscore",
    "trend": "trend",
    "relative_strength": "relativ styrke",
    "fundamentals": "fundamentale tall",
    "fundamental_history": "fundamental historikk",
    "profile_fit": "profilscore",
}

_PROFILE_MOMENTUM_LABEL = {
    "momentum": "markedsmoment",
    "quality": "kvalitet",
    "value": "value-profil",
    "cyclical": "syklisk profil",
}


def _normalize_question(question):
    return (question or "").lower().strip()


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


def _trend_rank(value):
    return _TREND_RANK.get(value, -1)


def _format_trend(value):
    if not value:
        return "—"
    return _TREND_DISPLAY.get(value, str(value))


def _format_number(value, decimals=1):
    numeric = _numeric(value)
    if numeric is None:
        return "—"

    formatted = f"{numeric:.{decimals}f}".replace(".", ",")
    if decimals == 0:
        return str(int(round(numeric)))
    return formatted


def _score_display(value):
    numeric = _numeric(value)
    if numeric is None:
        return None
    return int(round(numeric))


def _known_ticker_set(context):
    return set(_tickers_from_sources(context))


def _ticker_boundary_pattern(ticker):
    return re.compile(
        rf"(?<![a-z0-9.\-]){re.escape(str(ticker).lower())}(?![a-z0-9.\-])"
    )


def _is_valid_ticker_token(token, known_tickers):
    normalized = str(token or "").strip().upper()
    if not normalized or normalized in _TICKER_STOPWORDS:
        return False
    return normalized in known_tickers


def _dedupe_tickers_preserve_order(tickers):
    deduped = []
    seen = set()
    for ticker in tickers:
        normalized = str(ticker or "").strip().upper()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
        if len(deduped) >= COMPARISON_MAX_TICKERS:
            break
    return deduped


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
    primary_profile, score, _label = _profile_info(row)
    return score if score is not None else -1


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


def _deduplicate_screening_results(results):
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


def _format_percent(value):
    numeric = _numeric(value)
    if numeric is None:
        return "—"
    return f"{_format_number(numeric)} %"


def _confidence_label(confidence):
    return {
        "high": "Høy",
        "medium": "Middels",
        "low": "Lav",
    }.get(confidence, confidence)


def _merged_screening_snapshot(context):
    screening_results = context.get("screening_results") or {}
    frames = []

    for key in ("USA", "NORDEN", "OBX"):
        region_results = screening_results.get(key)
        if isinstance(region_results, pd.DataFrame) and not region_results.empty:
            frames.append(region_results)

    if not frames:
        return None

    merged = pd.concat(frames, ignore_index=True)
    return _deduplicate_screening_results(merged)


def _tickers_from_sources(context):
    tickers = set()

    for source in (
        context.get("watchlist") or [],
        context.get("watchlist_report"),
        context.get("portfolio_report"),
    ):
        if isinstance(source, list):
            tickers.update(str(ticker).strip().upper() for ticker in source if ticker)
            continue

        if isinstance(source, pd.DataFrame) and not source.empty:
            tickers.update(
                source["ticker"].astype(str).str.strip().str.upper().tolist()
            )

    merged = _merged_screening_snapshot(context)
    if merged is not None and not merged.empty:
        tickers.update(
            merged["ticker"].astype(str).str.strip().str.upper().tolist()
        )

    return sorted(tickers, key=len, reverse=True)


def find_ticker_row(ticker, context):
    normalized = str(ticker or "").strip().upper()
    if not normalized:
        return None

    stock = find_stock_analysis(
        normalized,
        context.get("watchlist_report"),
        context.get("portfolio_report"),
    )
    if stock is not None:
        return stock

    merged = _merged_screening_snapshot(context)
    if merged is not None and not merged.empty:
        match = merged[merged["ticker"].astype(str).str.upper() == normalized]
        if not match.empty:
            return match.iloc[0]

    return None


def _detect_screening_region(question):
    if "obx" in question:
        return "obx"

    for region, markers in _SCREENING_REGIONS.items():
        if region == "obx":
            continue
        if any(marker in question for marker in markers):
            return region

    if any(marker in question for marker in _SCREENING_REGIONS["obx"]):
        return "obx"

    return None


def _detect_strategy_profile(question):
    for profile, markers in _STRATEGY_PROFILES.items():
        if any(marker in question for marker in markers):
            return profile
    return None


def _parse_top_list_limit(question):
    match = re.search(r"\btopp?\s*(\d+)\b", question)
    if match:
        return min(int(match.group(1)), COMPARISON_MAX_TICKERS)

    if any(phrase in question for phrase in ("tre beste", "de tre beste", "topp tre", "top 3", "topp 3")):
        return COMPARISON_TOP_LIST_DEFAULT

    if "beste" in question or "sterkeste" in question or "sterkest" in question:
        return COMPARISON_TOP_LIST_DEFAULT

    return COMPARISON_TOP_LIST_DEFAULT


def _is_top_list_question(question):
    return any(
        phrase in question
        for phrase in (
            "beste",
            "sterkeste",
            "sterkest",
            "topp ",
            "top ",
            "tre beste",
            "de tre",
        )
    )


def _sort_by_score(results):
    if results is None or results.empty:
        return results

    return results.sort_values(
        by=["score"],
        ascending=[False],
        na_position="last",
    ).reset_index(drop=True)


def _filter_strategy_candidates(results, profile):
    if results is None or results.empty:
        return results

    if "primary_profile" not in results.columns:
        return results.iloc[0:0].copy()

    return results[results["primary_profile"] == profile].copy()


def _sort_strategy_candidates(results, profile):
    score_column = f"profile_score_{profile}"
    sort_columns = [score_column, "score"]
    available_columns = [
        column for column in sort_columns if column in results.columns
    ]

    if not available_columns:
        return _sort_by_score(results)

    return results.sort_values(
        by=available_columns,
        ascending=[False] * len(available_columns),
        na_position="last",
    ).reset_index(drop=True)


def resolve_top_list_tickers(question, context):
    question = _normalize_question(question)
    if not _is_top_list_question(question):
        return None

    limit = _parse_top_list_limit(question)
    profile = _detect_strategy_profile(question)

    if profile:
        merged = _merged_screening_snapshot(context)
        if merged is None or merged.empty:
            return None

        filtered = _filter_strategy_candidates(merged, profile)
        ranked = _sort_strategy_candidates(filtered, profile)
        if ranked.empty:
            return []
        return _dedupe_tickers_preserve_order(
            ranked["ticker"].head(limit).astype(str).str.upper().tolist()
        )

    region = _detect_screening_region(question)
    if region is None:
        return None

    snapshot_key = _SCREENING_SNAPSHOT_KEYS[region]
    screening_results = context.get("screening_results") or {}
    results = screening_results.get(snapshot_key)
    if results is None or not isinstance(results, pd.DataFrame) or results.empty:
        return None

    ranked = _sort_by_score(results)
    return _dedupe_tickers_preserve_order(
        ranked["ticker"].head(limit).astype(str).str.upper().tolist()
    )


def _extract_explicit_tickers(question, context):
    question = _normalize_question(question)
    known_tickers = _known_ticker_set(context)
    ordered = []
    seen = set()

    for ticker in sorted(known_tickers, key=len, reverse=True):
        for match in _ticker_boundary_pattern(ticker).finditer(question):
            if ticker not in seen:
                ordered.append((match.start(), ticker))
                seen.add(ticker)

    ordered.sort(key=lambda item: item[0])
    tickers = [ticker for _, ticker in ordered]

    regex_patterns = (
        r"\b(?:best av|sterkest av|hvilken av|sammenlign)\s+([a-z0-9.\-]+(?:\s+(?:og|eller|,)\s+[a-z0-9.\-]+)+)",
        r"\b([a-z0-9.\-]+)\s+(?:vs\.?|versus)\s+([a-z0-9.\-]+)",
        r"\b([a-z0-9.\-]+)\s+og\s+([a-z0-9.\-]+)",
        r"\b([a-z0-9.\-]+)\s+eller\s+([a-z0-9.\-]+)",
        r"\bbedre enn\s+([a-z0-9.\-]+)",
    )

    for pattern in regex_patterns:
        for match in re.finditer(pattern, question):
            for group in match.groups():
                if not group:
                    continue
                for part in re.split(r"\s+(?:og|eller|,)\s+", group):
                    candidate = str(part).strip().upper()
                    if not _is_valid_ticker_token(candidate, known_tickers):
                        continue
                    if candidate not in seen:
                        position = question.find(part.lower())
                        ordered.append((position if position >= 0 else len(question), candidate))
                        seen.add(candidate)

    ordered.sort(key=lambda item: item[0])
    tickers = _dedupe_tickers_preserve_order(ticker for _, ticker in ordered)
    return tickers


def _has_comparison_marker(question):
    if any(marker in question for marker in _COMPARISON_MARKERS):
        return True

    if re.search(r"\bvs\.?\b", question):
        return True

    return any(
        phrase in question
        for phrase in (
            "hvilken er best",
            "hvilken ser sterkest",
            "hvis jeg bare kan kjøpe én",
            "hvis jeg bare kan kjope en",
        )
    )


def is_comparison_question(question, context=None):
    question = _normalize_question(question)
    context = context or {}

    if any(marker in question for marker in _PORTFOLIO_COMPARISON_MARKERS):
        return False

    if "bedre ut enn" in question and any(
        phrase in question for phrase in ("det jeg eier", "det jeg har")
    ):
        return False

    if not _has_comparison_marker(question):
        return False

    if "sammenlign" in question and _is_top_list_question(question):
        return True

    explicit = _extract_explicit_tickers(question, context)
    if len(explicit) >= COMPARISON_MIN_TICKERS:
        return True

    if _is_top_list_question(question) and any(
        marker in question for marker in ("best av", "hvilken", "sterkest")
    ):
        return True

    return False


def resolve_comparison_tickers(question, context):
    question = _normalize_question(question)

    if "sammenlign" in question and _is_top_list_question(question):
        top_list = resolve_top_list_tickers(question, context)
        if top_list is None:
            return None, "Snapshot mangler screening-data. Kjør Oppdater analyser."
        if not top_list:
            return None, "Ingen kandidater funnet i snapshot for denne listen."
        if len(top_list) < COMPARISON_MIN_TICKERS:
            return None, (
                f"Fant bare {len(top_list)} kandidat i snapshot. "
                "Trenger minst to for sammenligning."
            )
        return top_list, None

    tickers = _extract_explicit_tickers(question, context)
    if len(tickers) < COMPARISON_MIN_TICKERS:
        return None, (
            "Spesifiser minst to tickere å sammenligne, for eksempel "
            "«Sammenlign SUBC.OL og AKRBP.OL»."
        )

    return _dedupe_tickers_preserve_order(tickers[:COMPARISON_MAX_TICKERS]), None


def _profile_info(row):
    primary_profile = _row_value(row, "primary_profile")
    primary_profile_score = None

    if primary_profile:
        score_column = f"profile_score_{primary_profile}"
        primary_profile_score = _numeric(_row_value(row, score_column))

    if primary_profile is None or primary_profile_score is None:
        try:
            profile = build_strategy_profile(row)
        except Exception:
            profile = None

        if profile:
            primary_profile = profile.get("primary_profile")
            profiles = profile.get("profiles") or {}
            primary_profile_score = _numeric(profiles.get(primary_profile))

    label = _PROFILE_LABELS.get(primary_profile, primary_profile or "—")
    return primary_profile, primary_profile_score, label


def _build_row(ticker, row, opportunity_item, analyst_item):
    primary_profile, primary_profile_score, profile_label = _profile_info(row)

    strengths = list((opportunity_item or {}).get("why_interesting") or [])
    risks = list((opportunity_item or {}).get("watch_out_for") or [])

    analyst_signal = None
    if analyst_item:
        analyst_signal = format_recommendation_label(
            analyst_item.get("recommendation_key")
        )

    return {
        "ticker": ticker,
        "score": _numeric(_row_value(row, "score")),
        "trend_regime": _row_value(row, "trend_regime"),
        "relative_strength_20d": _numeric(_row_value(row, "relative_strength_20d")),
        "fundamental_score": _numeric(_row_value(row, "fundamental_score")),
        "fundamental_history_score": _numeric(
            _row_value(row, "fundamental_history_score")
        ),
        "primary_profile": profile_label,
        "primary_profile_key": primary_profile,
        "primary_profile_score": primary_profile_score,
        "primary_profile_score_display": _score_display(primary_profile_score),
        "analyst_signal": analyst_signal,
        "analyst_recommendation_key": (
            str(analyst_item.get("recommendation_key")).strip().lower()
            if analyst_item and analyst_item.get("recommendation_key")
            else None
        ),
        "opportunity_headline": (opportunity_item or {}).get("headline"),
        "strengths": strengths,
        "risks": risks,
        "missing_fields": _missing_fields(row),
    }


def _missing_fields(row):
    missing = []
    checks = (
        ("score", "score"),
        ("trend_regime", "trend"),
        ("relative_strength_20d", "relativ styrke"),
        ("fundamental_score", "fundamentalt"),
        ("fundamental_history_score", "fundamental historikk"),
    )

    for key, label in checks:
        value = _row_value(row, key)
        if value is None or (isinstance(value, float) and pd.isna(value)):
            missing.append(label)

    return missing


def _category_winner(rows, key, higher_is_better=True, rank_fn=None):
    best_ticker = None
    best_value = None
    tied_tickers = []

    for row in rows:
        value = row.get(key)
        if rank_fn is not None:
            value = rank_fn(value)
        elif value is None:
            continue

        if best_value is None:
            best_value = value
            best_ticker = row["ticker"]
            tied_tickers = [row["ticker"]]
            continue

        if value == best_value:
            tied_tickers.append(row["ticker"])
            continue

        if higher_is_better and value > best_value:
            best_value = value
            best_ticker = row["ticker"]
            tied_tickers = [row["ticker"]]
        elif not higher_is_better and value < best_value:
            best_value = value
            best_ticker = row["ticker"]
            tied_tickers = [row["ticker"]]

    if len(tied_tickers) > 1:
        return None

    return best_ticker


def _compute_category_winners(rows):
    return {
        "total_score": _category_winner(rows, "score"),
        "trend": _category_winner(
            rows,
            "trend_regime",
            rank_fn=_trend_rank,
        ),
        "relative_strength": _category_winner(rows, "relative_strength_20d"),
        "fundamentals": _category_winner(rows, "fundamental_score"),
        "fundamental_history": _category_winner(rows, "fundamental_history_score"),
        "profile_fit": _category_winner(rows, "primary_profile_score_display"),
    }


def _sort_key_for_winner(row):
    return (
        _numeric(row.get("score")) or -1,
        _numeric(row.get("primary_profile_score")) or -1,
        _trend_rank(row.get("trend_regime")),
        _numeric(row.get("relative_strength_20d")) or -1,
        _numeric(row.get("fundamental_score")) or -1,
    )


def _pick_winner(rows, category_winners):
    if not rows:
        return None, "Ingen kandidater å sammenligne.", "low"

    ranked = sorted(rows, key=_sort_key_for_winner, reverse=True)
    top = ranked[0]
    second = ranked[1] if len(ranked) > 1 else None

    if second is None:
        return top["ticker"], "Kun én kandidat med data.", "low"

    top_score = _numeric(top.get("score"))
    second_score = _numeric(second.get("score"))

    if top_score is not None and second_score is not None:
        score_gap = top_score - second_score
    else:
        score_gap = 0

    top_key = _sort_key_for_winner(top)
    second_key = _sort_key_for_winner(second)

    if top_key == second_key:
        return None, "Det er ingen klar vinner.", "low"

    if (
        top_score is not None
        and second_score is not None
        and abs(top_score - second_score) <= 1
        and top_key[:2] == second_key[:2]
    ):
        return None, "Det er ingen klar vinner.", "low"

    winner = top["ticker"]
    winner_row = top

    categories_led = sum(
        1
        for ticker in category_winners.values()
        if ticker == winner
    )

    if categories_led >= 3 and score_gap >= 5:
        confidence = "high"
    elif score_gap <= COMPARISON_SCORE_TIE_GAP and categories_led <= 2:
        confidence = "low"
    else:
        confidence = "medium"

    reason_parts = []
    if category_winners.get("total_score") == winner:
        reason_parts.append("leder på totalscore")
    if category_winners.get("trend") == winner:
        reason_parts.append("sterkest trend")
    if category_winners.get("relative_strength") == winner:
        reason_parts.append("best relativ styrke")

    if not reason_parts:
        reason_parts.append("best samlet signal etter tie-breakers")

    reason = (
        f"{winner} er sterkest akkurat nå fordi den {', '.join(reason_parts)}."
    )

    strengths_against = []
    display_by_ticker = {
        row["ticker"]: row.get("primary_profile_score_display")
        for row in rows
    }
    for key, label in (
        ("fundamentals", "fundamentale tall"),
        ("fundamental_history", "fundamental historikk"),
        ("profile_fit", "profilscore"),
    ):
        leader = category_winners.get(key)
        if not leader or leader == winner:
            continue
        if key == "profile_fit":
            winner_display = display_by_ticker.get(winner)
            leader_display = display_by_ticker.get(leader)
            if winner_display is None or winner_display == leader_display:
                continue
        strengths_against.append(f"{leader} har bedre {label}")

    if strengths_against:
        reason += " " + "; ".join(strengths_against) + "."

    return winner, reason, confidence


def _build_caveats(rows):
    caveats = []
    profiles = {row.get("primary_profile_key") for row in rows if row.get("primary_profile_key")}

    if len(profiles) == 1 and "cyclical" in profiles:
        caveats.append(
            "Kandidatene er sykliske, så timing og risikostyring er viktig."
        )

    for row in rows:
        missing = row.get("missing_fields") or []
        if missing:
            caveats.append(
                f"{row['ticker']}: mangler {', '.join(missing)}."
            )

    return caveats


def _rows_by_ticker(rows):
    return {
        row["ticker"]: row
        for row in rows
        if row.get("ticker") and not row.get("missing")
    }


def _runner_up_row(rows, winner):
    others = [row for row in rows if row.get("ticker") != winner and not row.get("missing")]
    if not others:
        return None
    return max(others, key=lambda row: _numeric(row.get("score")) or -1)


def _analyst_rank(row):
    key = row.get("analyst_recommendation_key")
    if not key:
        return None
    return _ANALYST_RANK.get(str(key).strip().lower())


def _format_explanation_score(value):
    display = _score_display(value)
    if display is not None:
        return str(display)
    return _format_number(value, 0)


def _format_explanation_percent(value):
    numeric = _numeric(value)
    if numeric is None:
        return "—"
    return f"{_format_number(numeric)} %"


def _format_explanation_value(row, field):
    if field == "trend_regime":
        return _format_trend(row.get("trend_regime"))
    if field == "relative_strength_20d":
        return _format_explanation_percent(row.get("relative_strength_20d"))
    if field == "primary_profile_score_display":
        return _format_explanation_score(row.get("primary_profile_score_display"))
    if field in {"score", "fundamental_score", "fundamental_history_score"}:
        return _format_explanation_score(row.get(field))
    return str(row.get(field) or "—")


def _profile_label_for_row(row):
    key = row.get("primary_profile_key")
    if key:
        return _PROFILE_LABELS.get(key, str(key))
    return row.get("primary_profile") or "profil"


def _meaningfully_higher(winner_value, other_value, *, rank_fn=None):
    if winner_value is None or other_value is None:
        return False
    if rank_fn is not None:
        return rank_fn(winner_value) > rank_fn(other_value)
    return _numeric(winner_value) > _numeric(other_value)


def _meaningfully_lower(winner_value, other_value, *, rank_fn=None):
    if winner_value is None or other_value is None:
        return False
    if rank_fn is not None:
        return rank_fn(winner_value) < rank_fn(other_value)
    return _numeric(winner_value) < _numeric(other_value)


def _dedupe_bullets(bullets):
    seen = set()
    deduped = []
    for bullet in bullets:
        normalized = " ".join(str(bullet).lower().split())
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(bullet)
    return deduped


def _explanation_confidence(winner, rows, category_winners):
    if not winner:
        return "low"

    winner_row = _rows_by_ticker(rows).get(winner)
    runner_up = _runner_up_row(rows, winner)
    if winner_row is None or runner_up is None:
        return "low"

    leads_score = category_winners.get("total_score") == winner
    leads_trend = category_winners.get("trend") == winner
    leads_rs = category_winners.get("relative_strength") == winner

    winner_score = _numeric(winner_row.get("score")) or 0
    runner_up_score = _numeric(runner_up.get("score")) or 0
    score_gap = winner_score - runner_up_score

    important_losses = sum(
        1
        for key in ("fundamentals", "fundamental_history", "profile_fit")
        if category_winners.get(key) not in (None, winner)
    )

    if leads_score and leads_trend and leads_rs and score_gap >= 3:
        return "high"

    if not leads_score or score_gap <= 1:
        return "low"

    if leads_score and important_losses >= 1:
        return "medium"

    if leads_score and (leads_trend or leads_rs):
        return "medium"

    return "low"


def _best_other_for_category(rows, winner, field, *, rank_fn=None, higher_is_better=True):
    others = [row for row in rows if row.get("ticker") != winner and not row.get("missing")]
    best_row = None
    best_value = None

    for row in others:
        value = row.get(field)
        if rank_fn is not None:
            value = rank_fn(value)
        elif value is None:
            continue

        if best_value is None:
            best_value = value
            best_row = row
            continue

        if higher_is_better and value > best_value:
            best_value = value
            best_row = row
        elif not higher_is_better and value < best_value:
            best_value = value
            best_row = row

    return best_row


def _build_analyst_advantage(winner_row, other_rows, winner):
    winner_rank = _analyst_rank(winner_row)
    if winner_rank is None:
        return None

    other_ranks = [_analyst_rank(row) for row in other_rows if _analyst_rank(row) is not None]
    if not other_ranks:
        return None

    best_other_rank = max(other_ranks)
    if winner_rank > best_other_rank:
        return (
            f"Analytikerkonsensus støtter {winner} "
            f"({winner_row.get('analyst_signal')} vs svakere alternativer)."
        )
    if winner_rank < best_other_rank:
        return None
    return None


def _build_analyst_tradeoff(winner_row, other_rows, winner):
    winner_rank = _analyst_rank(winner_row)
    if winner_rank is None:
        return None

    best_other = None
    best_other_rank = None
    for row in other_rows:
        rank = _analyst_rank(row)
        if rank is None:
            continue
        if best_other_rank is None or rank > best_other_rank:
            best_other_rank = rank
            best_other = row

    if best_other is None or best_other_rank <= winner_rank:
        return None

    return (
        f"Analytikerne er mer positive til {best_other['ticker']} "
        f"({best_other.get('analyst_signal')} vs {winner_row.get('analyst_signal') or '—'})."
    )


def _build_opportunity_advantage(winner_row, winner):
    headline = winner_row.get("opportunity_headline")
    if not headline:
        return None
    return f"Opportunity Advisor: {headline}."


def _build_opportunity_tradeoff(winner_row):
    risks = winner_row.get("risks") or []
    if not risks:
        return None
    return f"Opportunity Advisor: {risks[0]}."


def _build_cyclical_tradeoff(winner_row, other_rows):
    if winner_row.get("primary_profile_key") != "cyclical":
        return None
    if all(row.get("primary_profile_key") == "cyclical" for row in other_rows):
        return "Syklisk profil gjør timing og risikostyring viktigere."
    return "Mer syklisk profil enn alternativene."


def _build_advantages(winner, winner_row, other_rows, category_winners):
    runner_up = _runner_up_row(other_rows + [winner_row], winner)
    if runner_up is None:
        runner_up = other_rows[0] if other_rows else winner_row

    advantages = []
    for category, _priority, field, template in _ADVANTAGE_SPECS:
        if category_winners.get(category) != winner:
            continue

        winner_value = _format_explanation_value(winner_row, field)
        other_value = _format_explanation_value(runner_up, field)
        rank_fn = _trend_rank if field == "trend_regime" else None

        if category != "total_score":
            raw_winner = winner_row.get(field if field != "trend_regime" else "trend_regime")
            raw_other = runner_up.get(field if field != "trend_regime" else "trend_regime")
            if not _meaningfully_higher(raw_winner, raw_other, rank_fn=rank_fn):
                continue

        advantages.append(
            (
                _priority,
                template.format(
                    winner=winner,
                    other=runner_up["ticker"],
                    winner_value=winner_value,
                    other_value=other_value,
                    profile_label=_profile_label_for_row(winner_row),
                ),
            )
        )

    analyst_advantage = _build_analyst_advantage(winner_row, other_rows, winner)
    if analyst_advantage:
        advantages.append((7, analyst_advantage))

    opportunity_advantage = _build_opportunity_advantage(winner_row, winner)
    if opportunity_advantage:
        advantages.append((8, opportunity_advantage))

    advantages.sort(key=lambda item: item[0])
    return _dedupe_bullets([text for _, text in advantages])[:_EXPLANATION_MAX_ADVANTAGES]


def _build_tradeoffs(winner, winner_row, other_rows, category_winners):
    tradeoffs = []

    for category, field, template in _TRADEOFF_SPECS:
        leader = category_winners.get(category)
        if leader in (None, winner):
            continue

        best_other = _rows_by_ticker(other_rows).get(leader) or _best_other_for_category(
            other_rows,
            winner,
            field,
            rank_fn=_trend_rank if field == "trend_regime" else None,
        )
        if best_other is None:
            continue

        rank_fn = _trend_rank if field == "trend_regime" else None
        raw_winner = winner_row.get(field if field != "trend_regime" else "trend_regime")
        raw_other = best_other.get(field if field != "trend_regime" else "trend_regime")
        if not _meaningfully_lower(raw_winner, raw_other, rank_fn=rank_fn):
            continue

        tradeoffs.append(
            template.format(
                winner=winner,
                best_other=best_other["ticker"],
                winner_value=_format_explanation_value(winner_row, field),
                other_value=_format_explanation_value(best_other, field),
            )
        )

    for builder in (
        lambda: _build_analyst_tradeoff(winner_row, other_rows, winner),
        lambda: _build_opportunity_tradeoff(winner_row),
        lambda: _build_cyclical_tradeoff(winner_row, other_rows),
    ):
        bullet = builder()
        if bullet:
            tradeoffs.append(bullet)

    tradeoffs = _dedupe_bullets(tradeoffs)
    if not tradeoffs and other_rows:
        runner_up = _runner_up_row(other_rows + [winner_row], winner)
        if runner_up is not None:
            tradeoffs.append(
                f"{runner_up['ticker']} er nærmere på score "
                f"({_format_explanation_score(runner_up.get('score'))} vs "
                f"{_format_explanation_score(winner_row.get('score'))})."
            )

    return tradeoffs[:_EXPLANATION_MAX_TRADEOFFS]


def _other_strengths_vs_winner(other_row, winner_row, category_winners, other_ticker):
    strengths = []
    for category, label in _CATEGORY_NARRATIVE.items():
        if category_winners.get(category) != other_ticker:
            continue
        if category == "profile_fit":
            profile_key = other_row.get("primary_profile_key")
            profile_phrase = _PROFILE_MOMENTUM_LABEL.get(profile_key, label)
            strengths.append(f"sterkere {profile_phrase}")
        else:
            strengths.append(f"bedre {label}")
    return strengths


def _other_weaknesses_vs_winner(other_row, winner_row, category_winners, winner):
    weaknesses = []
    for category, label in _CATEGORY_NARRATIVE.items():
        if category_winners.get(category) != winner:
            continue
        weaknesses.append(label)
    return weaknesses


def _build_why_not_the_others(winner, winner_row, other_rows, category_winners):
    bullets = []
    sorted_others = sorted(
        other_rows,
        key=lambda row: _numeric(row.get("score")) or -1,
        reverse=True,
    )

    for other_row in sorted_others[:_EXPLANATION_MAX_WHY_NOT]:
        other_ticker = other_row["ticker"]
        strengths = _other_strengths_vs_winner(
            other_row,
            winner_row,
            category_winners,
            other_ticker,
        )
        weaknesses = _other_weaknesses_vs_winner(
            other_row,
            winner_row,
            category_winners,
            winner,
        )

        if strengths and weaknesses:
            bullets.append(
                f"{other_ticker} har {', '.join(strengths)}, "
                f"men taper på {' og '.join(weaknesses)}."
            )
        elif strengths:
            bullets.append(
                f"{other_ticker} har {', '.join(strengths)}, "
                f"men lavere totalscore."
            )
        elif weaknesses:
            bullets.append(
                f"{other_ticker} taper på {' og '.join(weaknesses)}."
            )

    return _dedupe_bullets(bullets)[:_EXPLANATION_MAX_WHY_NOT]


def build_winner_explanation(comparison):
    rows = [
        row for row in comparison.get("rows") or []
        if not row.get("missing")
    ]
    winner = comparison.get("winner")
    category_winners = comparison.get("category_winners") or {}

    if len(rows) < COMPARISON_MIN_TICKERS:
        return {
            "summary": "Fant ikke nok data til en tydelig vurdering.",
            "advantages": [],
            "tradeoffs": [],
            "why_not_the_others": [],
            "confidence": "low",
        }

    if not winner:
        return {
            "summary": "Det er ingen klar vinner.",
            "advantages": [],
            "tradeoffs": [],
            "why_not_the_others": [],
            "confidence": "low",
        }

    winner_row = _rows_by_ticker(rows).get(winner)
    if winner_row is None:
        return {
            "summary": "Fant ikke nok data til en tydelig vurdering.",
            "advantages": [],
            "tradeoffs": [],
            "why_not_the_others": [],
            "confidence": "low",
        }

    other_rows = [row for row in rows if row["ticker"] != winner]
    advantages = _build_advantages(winner, winner_row, other_rows, category_winners)
    tradeoffs = _build_tradeoffs(winner, winner_row, other_rows, category_winners)
    why_not = _build_why_not_the_others(
        winner,
        winner_row,
        other_rows,
        category_winners,
    )
    confidence = _explanation_confidence(winner, rows, category_winners)

    if advantages:
        lead = advantages[0]
        if lead.endswith("."):
            lead = lead[:-1]
        summary = (
            f"{winner} er sterkest akkurat nå fordi "
            f"{lead[0].lower()}{lead[1:]}."
        )
    else:
        summary = (
            f"{winner} er sterkest akkurat nå basert på totalscore "
            f"og tie-breakers i snapshot-data."
        )

    return {
        "summary": summary,
        "advantages": advantages,
        "tradeoffs": tradeoffs,
        "why_not_the_others": why_not,
        "confidence": confidence,
    }


def build_comparison(tickers, context, universe_name=None):
    tickers = _dedupe_tickers_preserve_order(tickers)

    missing_tickers = []
    source_rows = []
    rows = []

    for ticker in tickers:
        row = find_ticker_row(ticker, context)
        if row is None:
            missing_tickers.append(ticker)
            continue
        source_rows.append(row)

    if missing_tickers:
        if len(missing_tickers) == len(tickers):
            return {
                "error": _MISSING_TICKER_MESSAGE.format(
                    ticker=", ".join(missing_tickers)
                ),
                "missing_tickers": missing_tickers,
            }

        for ticker in missing_tickers:
            rows.append(
                {
                    "ticker": ticker,
                    "missing": True,
                }
            )

    comparison_df = pd.DataFrame(source_rows) if source_rows else pd.DataFrame()
    analyst_summary = (
        context.get("analyst_summary")
        or (context.get("dashboard") or {}).get("analyst_summary")
        or {}
    )
    dashboard = context.get("dashboard") or {}

    opportunity_by_ticker = {}
    if not comparison_df.empty:
        advisor = build_opportunity_advisor(
            comparison_df,
            analyst_summary=analyst_summary,
            sentiment_summary=(
                context.get("sentiment_summary")
                or dashboard.get("sentiment_summary")
            ),
            earnings_summary=(
                context.get("earnings_summary")
                or dashboard.get("earnings_summary")
            ),
            news_summary=(
                context.get("news_summary") or dashboard.get("news_summary")
            ),
            limit=len(comparison_df),
            use_cache=True,
            universe_name=universe_name,
            full_results=comparison_df,
            is_full_universe=True,
        )
        opportunity_by_ticker = {
            item["ticker"]: item
            for item in advisor.get("items") or []
            if item.get("ticker")
        }

    for row in source_rows:
        ticker = str(_row_value(row, "ticker")).strip().upper()
        analyst_item = find_analyst_item(analyst_summary, ticker)
        built = _build_row(
            ticker,
            row,
            opportunity_by_ticker.get(ticker),
            analyst_item,
        )
        rows.append(built)

    valid_rows = [row for row in rows if not row.get("missing")]
    category_winners = _compute_category_winners(valid_rows)
    winner, winner_reason, confidence = _pick_winner(valid_rows, category_winners)

    comparison = {
        "tickers": tickers,
        "rows": rows,
        "winner": winner,
        "winner_reason": winner_reason,
        "category_winners": category_winners,
        "confidence": confidence,
        "caveats": _build_caveats(valid_rows),
        "missing_tickers": missing_tickers,
    }
    explanation = build_winner_explanation(comparison)
    comparison["winner_explanation"] = explanation
    comparison["confidence"] = explanation.get("confidence", confidence)
    comparison["winner_reason"] = explanation.get("summary", winner_reason)
    return comparison


def _comparison_title(tickers):
    if len(tickers) == 2:
        return f"Sammenligning: {tickers[0]} vs {tickers[1]}"
    return f"Sammenligning: {' vs '.join(tickers)}"


def _advantage_for_factor(values, higher_is_better=True, rank_fn=None):
    parsed = []
    for ticker, value in values:
        if rank_fn is not None:
            parsed_value = rank_fn(value)
        else:
            parsed_value = _numeric(value)

        if parsed_value is None:
            continue
        parsed.append((ticker, parsed_value))

    if not parsed:
        return "—"

    if higher_is_better:
        best = max(parsed, key=lambda item: item[1])
    else:
        best = min(parsed, key=lambda item: item[1])

    tied = [
        ticker
        for ticker, value in parsed
        if value == best[1]
    ]
    if len(tied) > 1:
        return "Jevnt"
    return best[0]


def format_comparison_answer(comparison):
    if comparison.get("error"):
        return comparison["error"]

    rows = [row for row in comparison.get("rows") or [] if not row.get("missing")]
    tickers = comparison.get("tickers") or []

    if len(rows) < COMPARISON_MIN_TICKERS:
        missing = comparison.get("missing_tickers") or tickers
        if missing:
            return _MISSING_TICKER_MESSAGE.format(ticker=", ".join(missing))
        return "Fant ikke nok data til sammenligning. Kjør Oppdater analyser."

    lines = [_comparison_title(tickers), ""]

    if len(rows) <= 2:
        ordered = []
        ticker_order = comparison.get("tickers") or [row["ticker"] for row in rows]
        rows_by_ticker = {row["ticker"]: row for row in rows}
        for ticker in ticker_order:
            if ticker in rows_by_ticker:
                ordered.append(rows_by_ticker[ticker])
        if len(ordered) == 2:
            rows = ordered

    if len(rows) <= 2:
        left, right = rows[0], rows[1]
        lines.extend(
            [
                f"| Faktor | {left['ticker']} | {right['ticker']} | Fordel |",
                "|---|---:|---:|---|",
                (
                    f"| Score | {_format_number(left.get('score'), 0)} | "
                    f"{_format_number(right.get('score'), 0)} | "
                    f"{_advantage_for_factor([(left['ticker'], left.get('score')), (right['ticker'], right.get('score'))])} |"
                ),
                (
                    f"| Trend | {_format_trend(left.get('trend_regime'))} | "
                    f"{_format_trend(right.get('trend_regime'))} | "
                    f"{_advantage_for_factor([(left['ticker'], left.get('trend_regime')), (right['ticker'], right.get('trend_regime'))], rank_fn=_trend_rank)} |"
                ),
                (
                    f"| Relativ styrke | {_format_percent(left.get('relative_strength_20d'))} | "
                    f"{_format_percent(right.get('relative_strength_20d'))} | "
                    f"{_advantage_for_factor([(left['ticker'], left.get('relative_strength_20d')), (right['ticker'], right.get('relative_strength_20d'))])} |"
                ),
                (
                    f"| Fundamentalt | {_format_number(left.get('fundamental_score'), 0)} | "
                    f"{_format_number(right.get('fundamental_score'), 0)} | "
                    f"{_advantage_for_factor([(left['ticker'], left.get('fundamental_score')), (right['ticker'], right.get('fundamental_score'))])} |"
                ),
                (
                    f"| Primær profil | {left.get('primary_profile')} "
                    f"{_format_number(left.get('primary_profile_score_display'), 0)} | "
                    f"{right.get('primary_profile')} "
                    f"{_format_number(right.get('primary_profile_score_display'), 0)} | "
                    f"{_advantage_for_factor([(left['ticker'], left.get('primary_profile_score_display')), (right['ticker'], right.get('primary_profile_score_display'))])} |"
                ),
            ]
        )
    else:
        header = "| Ticker | Score | Trend | RS | Fund | Profil |"
        separator = "|---|---:|---|---:|---:|---|"
        lines.extend([header, separator])
        for row in sorted(rows, key=lambda item: _numeric(item.get("score")) or -1, reverse=True):
            lines.append(
                f"| {row['ticker']} | {_format_number(row.get('score'), 0)} | "
                f"{_format_trend(row.get('trend_regime'))} | "
                f"{_format_percent(row.get('relative_strength_20d'))} | "
                f"{_format_number(row.get('fundamental_score'), 0)} | "
                f"{row.get('primary_profile')} {_format_number(row.get('primary_profile_score_display'), 0)} |"
            )

    lines.extend(["", "Kort vurdering", ""])
    explanation = comparison.get("winner_explanation") or {}
    summary = explanation.get("summary") or comparison.get("winner_reason")
    if summary:
        lines.append(summary)

    advantages = explanation.get("advantages") or []
    if advantages:
        lines.extend(["", "Hvorfor denne vinner"])
        for bullet in advantages:
            lines.append(f"• {bullet}")

    tradeoffs = explanation.get("tradeoffs") or []
    if tradeoffs:
        lines.extend(["", "Viktige kompromisser"])
        for bullet in tradeoffs:
            lines.append(f"• {bullet}")

    why_not = explanation.get("why_not_the_others") or []
    if why_not:
        lines.extend(["", "Hvorfor ikke de andre"])
        for bullet in why_not:
            lines.append(f"• {bullet}")

    winner = comparison.get("winner")
    lines.extend(["", "Samlet vurdering:", winner or "Det er ingen klar vinner."])
    lines.append(
        f"Sikkerhet: {_confidence_label(comparison.get('confidence', 'low'))}"
    )

    caveats = comparison.get("caveats") or []
    missing_tickers = comparison.get("missing_tickers") or []
    if missing_tickers:
        caveats = [
            _MISSING_TICKER_MESSAGE.format(ticker=ticker)
            for ticker in missing_tickers
        ] + caveats

    if caveats:
        lines.extend(["", "Viktigste forbehold:"])
        lines.extend(caveats)

    return "\n".join(lines)
