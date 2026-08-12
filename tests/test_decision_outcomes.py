from datetime import datetime, timezone

import pandas as pd

from src.decision_outcomes import (
    decision_outcome_path,
    evaluate_decision_journal,
    load_decision_outcomes,
    save_decision_outcomes,
)


def _entry(target=110.0, stop=95.0):
    return {
        "entry_id": "entry-1",
        "signal_date": "2026-01-02",
        "decision": {
            "ticker": "TEST",
            "action_code": "consider_buy",
            "target_price": target,
            "stop_level": stop,
        },
    }


def _prices(days=45):
    index = pd.bdate_range("2026-01-05", periods=days)
    close = [100.0 + index for index in range(days)]
    return pd.DataFrame(
        {
            "open": close,
            "high": [value + 2 for value in close],
            "low": [value - 2 for value in close],
            "close": close,
            "adjusted_close": close,
            "volume": [1000.0] * days,
        },
        index=index,
    )


def test_evaluates_next_open_and_all_horizons():
    outcomes = evaluate_decision_journal(
        [_entry()],
        price_loader=lambda _ticker: _prices(),
        evaluated_at=datetime(2026, 3, 10, tzinfo=timezone.utc),
    )

    outcome = outcomes[0]
    assert outcome["status"] == "complete"
    assert outcome["entry_date"] == "2026-01-05"
    assert outcome["entry_price"] == 100.0
    assert outcome["horizons"]["5"] == {
        "status": "complete",
        "exit_date": "2026-01-09",
        "return_pct": 4.0,
        "max_favorable_pct": 6.0,
        "max_adverse_pct": -2.0,
    }
    assert outcome["horizons"]["40"]["status"] == "complete"
    assert outcome["first_level_hit"]["event"] == "target"


def test_partial_evaluation_marks_unavailable_horizons_pending():
    outcome = evaluate_decision_journal(
        [_entry()],
        price_loader=lambda _ticker: _prices(days=7),
    )[0]

    assert outcome["status"] == "partial"
    assert outcome["horizons"]["5"]["status"] == "complete"
    assert outcome["horizons"]["10"]["status"] == "pending"


def test_less_than_first_horizon_remains_pending():
    outcome = evaluate_decision_journal(
        [_entry()],
        price_loader=lambda _ticker: _prices(days=2),
    )[0]

    assert outcome["status"] == "pending"


def test_stop_is_recorded_when_hit_before_target():
    prices = _prices(days=10)
    prices.iloc[0, prices.columns.get_loc("low")] = 94.0

    outcome = evaluate_decision_journal(
        [_entry()],
        price_loader=lambda _ticker: prices,
    )[0]

    assert outcome["first_level_hit"] == {
        "event": "stop",
        "date": "2026-01-05",
    }


def test_missing_prices_are_explicit_error():
    outcome = evaluate_decision_journal(
        [_entry()],
        price_loader=lambda _ticker: pd.DataFrame(),
    )[0]

    assert outcome["status"] == "error"
    assert outcome["message"] == "Prisdata mangler"


def test_outcomes_are_saved_and_loaded_atomically(tmp_path):
    path = tmp_path / "outcomes.json"
    outcomes = evaluate_decision_journal(
        [_entry()],
        price_loader=lambda _ticker: _prices(days=7),
    )

    assert save_decision_outcomes(outcomes, path) == path
    assert load_decision_outcomes(path) == outcomes
    assert save_decision_outcomes([], path) is None


def test_outcome_path_is_environment_separated(monkeypatch):
    monkeypatch.setenv("STOCK_AGENT_ENV", "test")
    assert decision_outcome_path().parts[-3:] == (
        "decision_journal_outcomes",
        "test",
        "outcomes.json",
    )
