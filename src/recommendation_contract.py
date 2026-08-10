from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.model_version import MODEL_VERSION


RECOMMENDATION_CONTRACT_VERSION = "1.0"
DEFAULT_TIME_HORIZON = "days_to_weeks"

RecommendationAction = Literal[
    "consider_buy",
    "hold",
    "avoid",
    "reduce_or_exit",
    "protect_position",
    "monitor",
    "prepare_event",
    "review",
    "wait",
    "remove_from_watchlist",
    "move_to_research",
]
RecommendationScope = Literal["portfolio", "watchlist", "candidate", "general"]
RecommendationConfidence = Literal["høy", "medium", "lav"]
DataQualityStatus = Literal["good", "limited", "insufficient", "not_assessed"]


class RecommendationDataQuality(BaseModel):
    status: DataQualityStatus = "not_assessed"
    as_of: str | None = None
    issues: list[str] = Field(default_factory=list)


class SupportingAction(BaseModel):
    action_code: RecommendationAction
    label: str
    reason: str
    source: str
    stop_level: float | None = None


class StructuredRecommendation(BaseModel):
    """Stable decision contract emitted by Recommendation Engine.

    Existing presentation and routing fields are accepted as extras during the
    migration. The fields declared here are the shared decision vocabulary for
    API, UI, chat and Decision Journal.
    """

    model_config = ConfigDict(extra="allow")

    contract_version: Literal["1.0"] = RECOMMENDATION_CONTRACT_VERSION
    model_version: str
    ticker: str = Field(min_length=1)
    action_code: RecommendationAction
    label: str | None = None
    scope: RecommendationScope
    time_horizon: Literal["days_to_weeks"] = DEFAULT_TIME_HORIZON
    entry_condition: str | None = None
    target_price: float | None = None
    stop_level: float | None = None
    reasons: list[str] = Field(min_length=1)
    invalidation: str | None = None
    confidence: RecommendationConfidence
    model_recommendation: str | None = None
    supporting_actions: list[SupportingAction] = Field(default_factory=list)
    material: bool = False
    data_quality: RecommendationDataQuality = Field(
        default_factory=RecommendationDataQuality
    )


_ACTION_BY_RULE = {
    "portfolio_reduser": "reduce_or_exit",
    "trailing_stop_triggered": "reduce_or_exit",
    "trailing_stop_near": "protect_position",
    "portfolio_monitor": "monitor",
    "earnings_prepare": "prepare_event",
    "earnings_critical": "prepare_event",
    "vurder_kjop": "consider_buy",
    "candidate": "consider_buy",
    "avvent_earnings": "wait",
    "watchlist_remove": "remove_from_watchlist",
    "watchlist_research": "move_to_research",
}

_SCOPE_BY_CATEGORY = {
    "Portefølje": "portfolio",
    "Risiko": "portfolio",
    "Watchlist": "watchlist",
    "Kjøpsmuligheter": "candidate",
    "Generelt": "general",
}


def action_code_for(rule: str | None) -> RecommendationAction:
    return _ACTION_BY_RULE.get(str(rule or "").strip(), "review")


def scope_for(category: str | None) -> RecommendationScope:
    return _SCOPE_BY_CATEGORY.get(str(category or "").strip(), "general")


def build_contract_fields(
    *,
    ticker: str,
    category: str,
    rule: str | None,
    reason: str,
    confidence: RecommendationConfidence,
    action_code: RecommendationAction | None = None,
    scope: RecommendationScope | None = None,
    label: str | None = None,
    entry_condition: str | None = None,
    target_price: float | None = None,
    stop_level: float | None = None,
    invalidation: str | None = None,
    data_quality: dict | RecommendationDataQuality | None = None,
    model_recommendation: str | None = None,
    supporting_actions: list[dict] | None = None,
    material: bool = False,
) -> dict:
    payload = {
        "contract_version": RECOMMENDATION_CONTRACT_VERSION,
        "model_version": MODEL_VERSION,
        "ticker": ticker,
        "action_code": action_code or action_code_for(rule),
        "label": label,
        "scope": scope or scope_for(category),
        "time_horizon": DEFAULT_TIME_HORIZON,
        "entry_condition": entry_condition,
        "target_price": target_price,
        "stop_level": stop_level,
        "reasons": [reason],
        "invalidation": invalidation,
        "confidence": confidence,
        "model_recommendation": model_recommendation,
        "supporting_actions": supporting_actions or [],
        "material": material,
        "data_quality": data_quality or RecommendationDataQuality(),
    }
    return StructuredRecommendation.model_validate(payload).model_dump()


def validate_recommendation(recommendation: dict) -> StructuredRecommendation:
    return StructuredRecommendation.model_validate(recommendation)
