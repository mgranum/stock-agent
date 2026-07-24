import pytest

from src.backtest_validation import (
    BACKTEST_VALIDATION_CHECKS,
    BLOCKED,
    PASS,
    ValidationCheck,
    build_backtest_validation_report,
    summarize_backtest_validation,
)
from src.model_version import MODEL_VERSION


def test_current_backtest_is_blocked_with_explicit_findings():
    report = build_backtest_validation_report()

    assert report["model_version"] == MODEL_VERSION
    assert report["validation_version"] == "backtest-validation-v1"
    assert report["approved"] is False
    assert report["status"] == BLOCKED
    assert report["blocked_count"] == 7
    assert len(report["checks"]) == len(BACKTEST_VALIDATION_CHECKS)


def test_report_can_pass_when_all_checks_pass():
    checks = (
        ValidationCheck(
            check_id="example",
            title="Eksempel",
            status=PASS,
            finding="Kontrollert.",
            required_action="Ingen.",
        ),
    )

    report = build_backtest_validation_report(checks)

    assert report["approved"] is True
    assert report["status"] == PASS
    assert report["blocked_count"] == 0
    assert summarize_backtest_validation(report).startswith(
        "Backtest-validering: GODKJENT"
    )


def test_empty_report_is_not_approved():
    report = build_backtest_validation_report(())

    assert report["approved"] is False
    assert report["status"] == BLOCKED
    assert summarize_backtest_validation(report) == (
        "Backtest-validering: ingen kontroller tilgjengelig."
    )


def test_invalid_check_status_is_rejected():
    checks = (
        ValidationCheck(
            check_id="invalid",
            title="Ugyldig",
            status="UNKNOWN",
            finding="Ukjent.",
            required_action="Rett status.",
        ),
    )

    with pytest.raises(ValueError, match="Ugyldig valideringsstatus"):
        build_backtest_validation_report(checks)
