from datetime import date

import pandas as pd

from src.discovery_validation import (
    build_discovery_journal,
    evaluate_discovery_journal,
    load_discovery_journal,
    save_discovery_journal,
    summarize_discovery_validation,
)


def _context():
    return {
        "model_version": "test-v1",
        "discovery_candidates": pd.DataFrame([
            {
                "ticker": "SECOND.ST",
                "source_universe": "NORDEN",
                "score": 90,
                "recommendation": "KJØP / ØK",
                "trend_regime": "STERK OPPTREND",
                "relative_strength_20d": 4.0,
                "fundamental_score": 70,
                "fundamental_history_score": 75,
                "primary_profile": "quality",
                "in_watchlist": False,
            },
            {
                "ticker": "FIRST",
                "source_universe": "USA",
                "score": 95,
                "recommendation": "KJØP / ØK",
                "trend_regime": "STERK OPPTREND",
                "relative_strength_20d": 5.0,
                "fundamental_score": 80,
                "fundamental_history_score": 85,
                "primary_profile": "momentum",
                "in_watchlist": False,
            },
        ]),
        "opportunity_advisor": {
            "items": [
                {"ticker": "FIRST"},
                {"ticker": "SECOND.ST"},
            ]
        },
    }


def _prices():
    index = pd.bdate_range("2026-01-05", periods=50)
    close = pd.Series(range(100, 150), index=index, dtype=float)
    return pd.DataFrame({
        "open": close,
        "high": close + 1,
        "low": close - 1,
        "close": close,
        "adjusted_close": close,
        "volume": 1_000_000.0,
    })


def _config():
    return {
        "execution": {"initial_cash": 100_000},
        "costs": {
            "spread_pct_per_side": 0,
            "usa": {
                "commission_pct": 0,
                "minimum_commission": 0,
                "fx_pct_per_side": 0,
            },
            "nordics": {
                "commission_pct": 0,
                "minimum_commission": 0,
                "fx_pct_per_side": 0,
            },
        },
    }


def test_builds_journal_from_candidates_shown_to_user():
    journal = build_discovery_journal(
        _context(),
        signal_date=date(2026, 1, 2),
    )

    assert journal["ticker"].tolist() == ["FIRST", "SECOND.ST"]
    assert journal["rank"].tolist() == [1, 2]
    assert journal["region"].tolist() == ["USA", "NORDEN"]
    assert journal["global_benchmark"].unique().tolist() == ["ACWI"]
    assert journal.loc[1, "local_benchmark"] == "^OMX"


def test_save_overwrites_same_day_and_loads_without_duplicates(tmp_path):
    path = tmp_path / "discovery_2026-01-02.csv"

    save_discovery_journal(
        _context(),
        signal_date=date(2026, 1, 2),
        path=path,
    )
    save_discovery_journal(
        _context(),
        signal_date=date(2026, 1, 2),
        path=path,
    )

    loaded = load_discovery_journal(tmp_path)
    assert len(loaded) == 2


def test_evaluates_next_day_execution_and_equal_weight_cohort():
    journal = build_discovery_journal(
        {
            **_context(),
            "discovery_candidates": _context()["discovery_candidates"].iloc[[1]],
            "opportunity_advisor": {"items": [{"ticker": "FIRST"}]},
        },
        signal_date=date(2026, 1, 2),
    )

    evaluation = evaluate_discovery_journal(
        journal,
        price_loader=lambda _symbol: _prices(),
        config=_config(),
        horizons=(5, 40, 60),
    )

    assert evaluation["status"].tolist() == [
        "complete",
        "complete",
        "pending",
    ]
    assert evaluation.iloc[0]["entry_date"] == "2026-01-05"
    assert evaluation.iloc[0]["exit_date"] == "2026-01-09"
    assert evaluation.iloc[0]["global_difference_pct"] == 0

    summary = summarize_discovery_validation(evaluation)
    assert summary["completed"] == 2
    assert summary["pending"] == 1
    assert summary["cohort_count"] == 2
