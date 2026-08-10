import pytest
from pydantic import ValidationError

from src.model_version import MODEL_VERSION
from src.recommendation_contract import (
    DEFAULT_TIME_HORIZON,
    RECOMMENDATION_CONTRACT_VERSION,
    build_contract_fields,
    validate_recommendation,
)


def test_builds_complete_contract_without_inventing_missing_levels():
    decision = build_contract_fields(
        ticker="NVDA",
        category="Kjøpsmuligheter",
        rule="candidate",
        reason="Sterk trend og kvalitet.",
        confidence="høy",
    )

    assert decision == {
        "contract_version": RECOMMENDATION_CONTRACT_VERSION,
        "model_version": MODEL_VERSION,
        "ticker": "NVDA",
        "action_code": "consider_buy",
        "scope": "candidate",
        "time_horizon": DEFAULT_TIME_HORIZON,
        "entry_condition": None,
        "target_price": None,
        "stop_level": None,
        "reasons": ["Sterk trend og kvalitet."],
        "invalidation": None,
        "confidence": "høy",
        "data_quality": {
            "status": "not_assessed",
            "as_of": None,
            "issues": [],
        },
    }


@pytest.mark.parametrize(
    ("category", "rule", "action_code", "scope"),
    [
        ("Portefølje", "portfolio_reduser", "reduce_or_exit", "portfolio"),
        ("Portefølje", "trailing_stop_near", "protect_position", "portfolio"),
        ("Risiko", "earnings_critical", "prepare_event", "portfolio"),
        ("Watchlist", "avvent_earnings", "wait", "watchlist"),
        ("Watchlist", "watchlist_remove", "remove_from_watchlist", "watchlist"),
        ("Generelt", "unknown", "review", "general"),
    ],
)
def test_maps_existing_rules_without_changing_their_priority(
    category, rule, action_code, scope
):
    decision = build_contract_fields(
        ticker="AAPL",
        category=category,
        rule=rule,
        reason="Test",
        confidence="medium",
    )

    assert decision["action_code"] == action_code
    assert decision["scope"] == scope


def test_rejects_invalid_contract_values():
    with pytest.raises(ValidationError):
        validate_recommendation(
            {
                "contract_version": "1.0",
                "model_version": MODEL_VERSION,
                "ticker": "AAPL",
                "action_code": "buy_now",
                "scope": "portfolio",
                "time_horizon": "intraday",
                "reasons": ["Test"],
                "confidence": "høy",
            }
        )
