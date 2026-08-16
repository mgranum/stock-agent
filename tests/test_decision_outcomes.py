from datetime import datetime, timezone

import pandas as pd

from src.decision_outcomes import (
    build_decision_outcome_report,
    decision_outcome_path,
    evaluate_decision_journal,
    load_decision_outcomes,
    save_decision_outcomes,
)


def _entry(target=110.0, stop=95.0, technical_action=None):
    entry = {
        "entry_id": "entry-1",
        "signal_date": "2026-01-02",
        "evidence": {
            "region": "usa",
            "primary_profile": "momentum",
        },
        "decision": {
            "ticker": "TEST",
            "action_code": "consider_buy",
            "target_price": target,
            "stop_level": stop,
        },
    }
    if technical_action is not None:
        entry["evidence"]["technical_reference"] = {
            "version": "trend_momentum_v1",
            "status": "complete",
            "action": technical_action,
            "rule_fingerprint": "technical-rule-v1",
        }
    return entry


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


def _benchmark_prices(days=45):
    prices = _prices(days=days)
    prices[["open", "high", "low", "close", "adjusted_close"]] = (
        prices[["open", "high", "low", "close", "adjusted_close"]]
        .sub(100.0)
        .mul(2.0)
        .add(100.0)
    )
    return prices


def _price_loader(symbol):
    return _benchmark_prices() if symbol == "ACWI" else _prices()


def _validation_config(
    *,
    initial_cash=100_000,
    minimum_commission=0,
    spread_pct_per_side=0,
):
    profile = {
        "commission_pct": 0,
        "minimum_commission": minimum_commission,
        "fx_pct_per_side": 0,
    }
    return {
        "execution": {"initial_cash": initial_cash},
        "costs": {
            "spread_pct_per_side": spread_pct_per_side,
            "usa": dict(profile),
            "nordics": dict(profile),
        },
    }


def test_evaluates_next_open_and_all_horizons():
    outcomes = evaluate_decision_journal(
        [_entry()],
        price_loader=_price_loader,
        evaluated_at=datetime(2026, 3, 10, tzinfo=timezone.utc),
        validation_config=_validation_config(),
    )

    outcome = outcomes[0]
    assert outcome["status"] == "complete"
    assert outcome["entry_date"] == "2026-01-05"
    assert outcome["entry_price"] == 100.0
    assert outcome["region"] == "usa"
    assert outcome["primary_profile"] == "momentum"
    assert outcome["horizons"]["5"] == {
        "status": "complete",
        "exit_date": "2026-01-09",
        "return_pct": 4.0,
        "max_favorable_pct": 6.0,
        "max_adverse_pct": -2.0,
        "benchmark_status": "complete",
        "benchmark_return_pct": 8.0,
        "relative_return_pct": -4.0,
        "cost_status": "complete",
        "net_return_pct": 4.0,
        "benchmark_net_return_pct": 8.0,
        "net_relative_return_pct": -4.0,
        "local_benchmark_status": "complete",
        "local_benchmark_return_pct": 4.0,
        "local_relative_return_pct": 0.0,
        "local_cost_status": "complete",
        "local_benchmark_net_return_pct": 4.0,
        "local_net_relative_return_pct": 0.0,
    }
    assert outcome["horizons"]["40"]["status"] == "complete"
    assert outcome["first_level_hit"]["event"] == "target"
    assert outcome["benchmark"] == {
        "symbol": "ACWI",
        "status": "complete",
        "entry_date": "2026-01-05",
        "entry_price": 100.0,
    }
    assert outcome["local_benchmark"] == {
        "symbol": "SPY",
        "label": "USA",
        "status": "complete",
        "entry_date": "2026-01-05",
        "entry_price": 100.0,
    }


def test_partial_evaluation_marks_unavailable_horizons_pending():
    outcome = evaluate_decision_journal(
        [_entry()],
        price_loader=lambda _ticker: _prices(days=7),
        validation_config=_validation_config(),
    )[0]

    assert outcome["status"] == "partial"
    assert outcome["horizons"]["5"]["status"] == "complete"
    assert outcome["horizons"]["10"]["status"] == "pending"


def test_less_than_first_horizon_remains_pending():
    outcome = evaluate_decision_journal(
        [_entry()],
        price_loader=lambda _ticker: _prices(days=2),
        validation_config=_validation_config(),
    )[0]

    assert outcome["status"] == "pending"


def test_stop_is_recorded_when_hit_before_target():
    prices = _prices(days=10)
    prices.iloc[0, prices.columns.get_loc("low")] = 94.0

    outcome = evaluate_decision_journal(
        [_entry()],
        price_loader=lambda _ticker: prices,
        validation_config=_validation_config(),
    )[0]

    assert outcome["first_level_hit"] == {
        "event": "stop",
        "date": "2026-01-05",
    }


def test_missing_prices_are_explicit_error():
    outcome = evaluate_decision_journal(
        [_entry()],
        price_loader=lambda _ticker: pd.DataFrame(),
        validation_config=_validation_config(),
    )[0]

    assert outcome["status"] == "error"
    assert outcome["message"] == "Prisdata mangler"


def test_missing_benchmark_preserves_stock_outcome_and_marks_comparison_error():
    def loader(symbol):
        return pd.DataFrame() if symbol == "ACWI" else _prices()

    outcome = evaluate_decision_journal(
        [_entry()],
        price_loader=loader,
        validation_config=_validation_config(),
    )[0]

    assert outcome["status"] == "complete"
    assert outcome["benchmark"] == {
        "symbol": "ACWI",
        "status": "error",
        "message": "Benchmarkdata mangler",
    }
    assert outcome["horizons"]["5"]["benchmark_status"] == "error"


def test_cost_adjusted_returns_preserve_gross_values_and_record_assumptions():
    outcome = evaluate_decision_journal(
        [_entry()],
        price_loader=_price_loader,
        validation_config=_validation_config(
            initial_cash=1_000,
            minimum_commission=10,
            spread_pct_per_side=0.001,
        ),
    )[0]

    horizon = outcome["horizons"]["5"]
    assert horizon["return_pct"] == 4.0
    assert horizon["benchmark_return_pct"] == 8.0
    assert horizon["cost_status"] == "complete"
    assert horizon["net_return_pct"] < horizon["return_pct"]
    assert horizon["benchmark_net_return_pct"] < horizon["benchmark_return_pct"]
    assert horizon["net_relative_return_pct"] == round(
        horizon["net_return_pct"] - horizon["benchmark_net_return_pct"],
        4,
    )
    assert outcome["cost_evaluation"]["status"] == "complete"
    assert outcome["cost_evaluation"]["initial_capital"] == 1_000
    assert len(outcome["cost_evaluation"]["fingerprint"]) == 16


def test_uses_ticker_market_benchmark_for_local_comparison():
    entry = _entry()
    entry["decision"]["ticker"] = "TEST.OL"

    outcome = evaluate_decision_journal(
        [entry],
        price_loader=lambda symbol: (
            _benchmark_prices() if symbol == "ACWI" else _prices()
        ),
        validation_config=_validation_config(),
    )[0]

    assert outcome["local_benchmark"]["symbol"] == "OSEBX.OL"
    assert outcome["local_benchmark"]["label"] == "Norge"
    assert outcome["horizons"]["5"]["local_benchmark_status"] == "complete"
    assert outcome["horizons"]["5"]["local_net_relative_return_pct"] == 0.0


def test_local_benchmark_error_does_not_invalidate_acwi_comparison():
    entry = _entry()
    entry["decision"]["ticker"] = "TEST.OL"

    def loader(symbol):
        if symbol == "OSEBX.OL":
            return pd.DataFrame()
        return _benchmark_prices() if symbol == "ACWI" else _prices()

    outcome = evaluate_decision_journal(
        [entry],
        price_loader=loader,
        validation_config=_validation_config(),
    )[0]

    assert outcome["benchmark"]["status"] == "complete"
    assert outcome["horizons"]["5"]["cost_status"] == "complete"
    assert outcome["local_benchmark"]["status"] == "error"
    assert outcome["local_benchmark"]["message"] == "Benchmarkdata mangler"


def test_technical_reference_uses_same_stock_and_costs_or_stays_in_cash():
    cash_outcome = evaluate_decision_journal(
        [_entry(technical_action="cash")],
        price_loader=_price_loader,
        validation_config=_validation_config(),
    )[0]
    buy_outcome = evaluate_decision_journal(
        [_entry(technical_action="buy")],
        price_loader=_price_loader,
        validation_config=_validation_config(),
    )[0]

    cash_horizon = cash_outcome["horizons"]["5"]
    assert cash_outcome["technical_reference"]["evaluation_status"] == "complete"
    assert cash_horizon["technical_reference_net_return_pct"] == 0.0
    assert cash_horizon["model_vs_technical_net_return_pct"] == 4.0

    buy_horizon = buy_outcome["horizons"]["5"]
    assert buy_horizon["technical_reference_net_return_pct"] == 4.0
    assert buy_horizon["model_vs_technical_net_return_pct"] == 0.0


def test_legacy_advice_is_not_backfilled_with_current_technical_signal():
    outcome = evaluate_decision_journal(
        [_entry()],
        price_loader=_price_loader,
        validation_config=_validation_config(),
    )[0]

    assert outcome["technical_reference"]["status"] == "unavailable"
    assert outcome["technical_reference"]["evaluation_status"] == "unavailable"
    assert "technical_reference_status" not in outcome["horizons"]["5"]


def test_outcomes_are_saved_and_loaded_atomically(tmp_path):
    path = tmp_path / "outcomes.json"
    outcomes = evaluate_decision_journal(
        [_entry()],
        price_loader=lambda _ticker: _prices(days=7),
        validation_config=_validation_config(),
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


def _complete_outcome(
    action="consider_buy",
    return_pct=5.0,
    benchmark_return_pct=3.0,
    region="usa",
    primary_profile="quality",
    net_return_pct=None,
    benchmark_net_return_pct=None,
    local_benchmark="SPY",
    local_benchmark_return_pct=4.0,
    local_benchmark_net_return_pct=None,
    technical_action=None,
    technical_rule_fingerprint="technical-rule-v1",
):
    net_return_pct = return_pct if net_return_pct is None else net_return_pct
    benchmark_net_return_pct = (
        benchmark_return_pct
        if benchmark_net_return_pct is None
        else benchmark_net_return_pct
    )
    local_benchmark_net_return_pct = (
        local_benchmark_return_pct
        if local_benchmark_net_return_pct is None
        else local_benchmark_net_return_pct
    )
    outcome = {
        "action_code": action,
        "region": region,
        "primary_profile": primary_profile,
        "status": "complete",
        "cost_evaluation": {
            "status": "complete",
            "fingerprint": "test-cost-model",
            "initial_capital": 100_000,
        },
        "local_benchmark": {
            "symbol": local_benchmark,
            "status": "complete",
        },
        "horizons": {
            str(days): {
                "status": "complete",
                "return_pct": return_pct,
                "max_favorable_pct": return_pct + 2,
                "max_adverse_pct": -2.0,
                "benchmark_status": "complete",
                "benchmark_return_pct": benchmark_return_pct,
                "relative_return_pct": return_pct - benchmark_return_pct,
                "cost_status": "complete",
                "net_return_pct": net_return_pct,
                "benchmark_net_return_pct": benchmark_net_return_pct,
                "net_relative_return_pct": (
                    net_return_pct - benchmark_net_return_pct
                ),
                "local_benchmark_status": "complete",
                "local_benchmark_return_pct": local_benchmark_return_pct,
                "local_relative_return_pct": (
                    return_pct - local_benchmark_return_pct
                ),
                "local_cost_status": "complete",
                "local_benchmark_net_return_pct": (
                    local_benchmark_net_return_pct
                ),
                "local_net_relative_return_pct": (
                    net_return_pct - local_benchmark_net_return_pct
                ),
            }
            for days in (5, 10, 20, 40)
        },
    }
    if technical_action is not None:
        outcome["technical_reference"] = {
            "version": "trend_momentum_v1",
            "status": "complete",
            "action": technical_action,
            "rule_fingerprint": technical_rule_fingerprint,
            "evaluation_status": "complete",
        }
        for result in outcome["horizons"].values():
            reference_return = return_pct if technical_action == "buy" else 0.0
            reference_net_return = (
                net_return_pct if technical_action == "buy" else 0.0
            )
            result.update(
                {
                    "technical_reference_status": "complete",
                    "technical_reference_return_pct": reference_return,
                    "technical_reference_net_return_pct": reference_net_return,
                    "model_vs_technical_return_pct": (
                        return_pct - reference_return
                    ),
                    "model_vs_technical_net_return_pct": (
                        net_return_pct - reference_net_return
                    ),
                }
            )
    return outcome


def test_report_hides_statistics_when_coverage_is_too_low():
    report = build_decision_outcome_report([_complete_outcome()] * 2)

    assert report["status"] == "collecting"
    assert report["status_label"] == "For lite data"
    assert report["complete_40d"] == 2
    assert report["minimum_complete_40d"] == 60
    assert all(item["statistics"] is None for item in report["horizons"])


def test_report_exposes_descriptive_statistics_at_horizon_threshold():
    outcomes = [
        _complete_outcome(return_pct=5.0),
        *[_complete_outcome(return_pct=-1.0) for _ in range(29)],
    ]

    report = build_decision_outcome_report(outcomes)
    horizon_5 = next(item for item in report["horizons"] if item["days"] == 5)

    assert horizon_5["sufficient"] is True
    assert horizon_5["statistics"] == {
        "average_return_pct": -0.8,
        "median_return_pct": -1.0,
        "positive_return_pct": 3.3,
        "average_max_favorable_pct": 1.2,
        "average_max_adverse_pct": -2.0,
    }
    assert report["overall_ready"] is False


def test_report_requires_60_complete_40_day_outcomes_for_overall_readiness():
    report = build_decision_outcome_report([_complete_outcome()] * 60)

    assert report["status"] == "ready"
    assert report["overall_ready"] is True
    assert report["actions"] == [
        {"action_code": "consider_buy", "total": 60, "complete_40d": 60}
    ]
    assert report["benchmark"]["status"] == "ready"
    assert report["benchmark"]["complete_40d"] == 60
    assert report["benchmark"]["decision_gate"]["evaluated"] is True


def test_benchmark_report_exposes_relative_statistics_at_threshold():
    outcomes = [
        _complete_outcome(return_pct=5.0, benchmark_return_pct=3.0),
        *[
            _complete_outcome(return_pct=1.0, benchmark_return_pct=2.0)
            for _ in range(29)
        ],
    ]

    report = build_decision_outcome_report(outcomes)
    horizon = report["benchmark"]["horizons"][0]

    assert horizon["sufficient"] is True
    assert horizon["statistics"] == {
        "average_stock_return_pct": 1.13,
        "average_benchmark_return_pct": 2.03,
        "average_relative_return_pct": -0.9,
        "median_relative_return_pct": -1.0,
        "trimmed_average_relative_return_pct": -1.0,
        "benchmark_win_pct": 3.3,
        "average_net_return_pct": 1.13,
        "average_benchmark_net_return_pct": 2.03,
        "average_net_relative_return_pct": -0.9,
        "median_net_relative_return_pct": -1.0,
        "trimmed_average_net_relative_return_pct": -1.0,
        "net_benchmark_win_pct": 3.3,
    }


def test_benchmark_report_excludes_non_buy_actions():
    outcomes = [
        _complete_outcome(action="consider_buy"),
        _complete_outcome(action="reduce_or_exit", return_pct=-10.0),
    ]

    report = build_decision_outcome_report(
        outcomes,
        min_mature_per_horizon=1,
        min_complete_40d=1,
    )

    assert report["benchmark"]["eligible_outcomes"] == 1
    assert report["benchmark"]["horizons"][0]["complete"] == 1
    assert report["benchmark"]["horizons"][0]["statistics"][
        "average_net_relative_return_pct"
    ] == 2.0


def test_local_benchmark_report_is_separate_and_coverage_gated_per_market():
    outcomes = [
        *[
            _complete_outcome(local_benchmark="SPY")
            for _ in range(30)
        ],
        *[
            _complete_outcome(
                region="norway",
                local_benchmark="OSEBX.OL",
            )
            for _ in range(29)
        ],
    ]

    report = build_decision_outcome_report(outcomes)["local_benchmarks"]
    markets = {item["symbol"]: item for item in report["benchmarks"]}
    spy_5d = markets["SPY"]["horizons"][0]
    osebx_5d = markets["OSEBX.OL"]["horizons"][0]

    assert report["status"] == "collecting"
    assert markets["SPY"]["label"] == "USA"
    assert markets["OSEBX.OL"]["label"] == "Norge"
    assert spy_5d["sufficient"] is True
    assert spy_5d["statistics"]["average_net_relative_return_pct"] == 1.0
    assert osebx_5d["sufficient"] is False
    assert osebx_5d["statistics"] is None


def test_technical_reference_report_is_separate_and_coverage_gated():
    outcomes = [
        *[
            _complete_outcome(technical_action="buy")
            for _ in range(15)
        ],
        *[
            _complete_outcome(technical_action="cash")
            for _ in range(15)
        ],
    ]

    report = build_decision_outcome_report(outcomes)["technical_reference"]
    horizon = report["horizons"][0]

    assert report["status"] == "ready"
    assert report["eligible_outcomes"] == 30
    assert report["classified_outcomes"] == 30
    assert report["buy_signals"] == 15
    assert report["cash_signals"] == 15
    assert horizon["statistics"] == {
        "average_model_net_return_pct": 5.0,
        "average_reference_net_return_pct": 2.5,
        "average_net_difference_pct": 2.5,
        "median_net_difference_pct": 2.5,
        "trimmed_average_net_difference_pct": 2.32,
        "model_win_pct": 50.0,
    }


def test_technical_reference_does_not_backfill_or_mix_rule_versions():
    unavailable = build_decision_outcome_report(
        [_complete_outcome()]
    )["technical_reference"]
    mixed = build_decision_outcome_report(
        [
            *[
                _complete_outcome(
                    technical_action="cash",
                    technical_rule_fingerprint="rule-a",
                )
                for _ in range(15)
            ],
            *[
                _complete_outcome(
                    technical_action="cash",
                    technical_rule_fingerprint="rule-b",
                )
                for _ in range(15)
            ],
        ]
    )["technical_reference"]

    assert unavailable["classified_outcomes"] == 0
    assert unavailable["unavailable_outcomes"] == 1
    assert mixed["rule_consistent"] is False
    assert mixed["horizons"][0]["statistics"] is None


def test_decision_gate_stays_collecting_before_60_complete_40_day_outcomes():
    report = build_decision_outcome_report([_complete_outcome()] * 59)

    gate = report["benchmark"]["decision_gate"]
    assert gate["status"] == "collecting"
    assert gate["evaluated"] is False
    assert all(check["status"] == "pending" for check in gate["checks"])


def test_decision_gate_passes_only_with_robust_region_and_profile_breadth():
    outcomes = [
        *[
            _complete_outcome(region="usa", primary_profile="quality")
            for _ in range(30)
        ],
        *[
            _complete_outcome(region="norway", primary_profile="momentum")
            for _ in range(30)
        ],
    ]

    report = build_decision_outcome_report(outcomes)
    benchmark = report["benchmark"]

    assert benchmark["decision_gate"]["status"] == "passed"
    assert benchmark["decision_gate"]["version"] == "2026.08.15-v2"
    assert all(
        check["status"] == "passed"
        for check in benchmark["decision_gate"]["checks"]
    )
    assert benchmark["segments"]["regions"]["positive_segments"] == 2
    assert benchmark["segments"]["profiles"]["positive_segments"] == 2


def test_decision_gate_fails_when_results_depend_on_one_profile():
    outcomes = [
        _complete_outcome(region="usa", primary_profile="quality")
        for _ in range(60)
    ]

    gate = build_decision_outcome_report(outcomes)["benchmark"]["decision_gate"]

    assert gate["status"] == "failed"
    failed = {item["check_id"] for item in gate["checks"] if item["status"] == "failed"}
    assert "profiles_concentration" in failed
    assert "profiles_breadth" in failed


def test_decision_gate_uses_net_not_gross_relative_returns():
    outcomes = [
        *[
            _complete_outcome(
                region="usa",
                primary_profile="quality",
                return_pct=5.0,
                benchmark_return_pct=3.0,
                net_return_pct=1.0,
                benchmark_net_return_pct=2.0,
            )
            for _ in range(30)
        ],
        *[
            _complete_outcome(
                region="norway",
                primary_profile="momentum",
                return_pct=5.0,
                benchmark_return_pct=3.0,
                net_return_pct=1.0,
                benchmark_net_return_pct=2.0,
            )
            for _ in range(30)
        ],
    ]

    benchmark = build_decision_outcome_report(outcomes)["benchmark"]
    gate = benchmark["decision_gate"]

    assert benchmark["horizons"][1]["statistics"][
        "average_relative_return_pct"
    ] == 2.0
    assert benchmark["horizons"][1]["statistics"][
        "average_net_relative_return_pct"
    ] == -1.0
    assert gate["status"] == "failed"
    assert any(
        item["check_id"] == "positive_average_20d"
        and item["status"] == "failed"
        for item in gate["checks"]
    )
