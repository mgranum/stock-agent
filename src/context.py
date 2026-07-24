from __future__ import annotations

import json
from datetime import date, datetime, timezone
from io import StringIO
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.advisor import build_advisor_details, build_advisor_output
from src.alerts import build_alerts
from src.analysis import analyze_watchlist
from src.analyst import build_analyst_summary
from src.dashboard import build_dashboard, build_portfolio_risk
from src.daily_briefing import build_daily_briefing
from src.recommendation_engine import build_recommendations
from src.daily_flow import build_daily_flow
from src.earnings import build_earnings_summary
from src.news import build_news_summary
from src.portfolio import analyze_portfolio, ensure_portfolio_report, summarize_portfolio
from src.environment import context_snapshot_filename
from src.config import load_watchlists
from src.model_version import MODEL_VERSION
from src.sentiment import build_sentiment_summary, merge_sentiment_into_news_summary
from src.screener import screen_nordics, screen_obx, screen_us_large
from src.watchlist_advisor import build_watchlist_advisor

CONTEXT_SNAPSHOT_VERSION = 1
SCREENING_SNAPSHOT_PRESET = "Beste kandidater"
SCREENING_SNAPSHOT_LIMIT = 5
_DATAFRAME_MARKER = "__type__"
_DATAFRAME_TYPE = "dataframe"


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def context_snapshot_path() -> Path:
    cache_dir = _project_root() / "cache"
    cache_dir.mkdir(exist_ok=True)
    return cache_dir / context_snapshot_filename()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _parse_iso_datetime(value: Any) -> datetime | None:
    if not value:
        return None

    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)

    return parsed


def _serialize_dataframe(df: pd.DataFrame) -> dict[str, Any]:
    split_payload = json.loads(
        df.to_json(orient="split", date_format="iso")
    )
    return {
        _DATAFRAME_MARKER: _DATAFRAME_TYPE,
        **split_payload,
    }


def _deserialize_dataframe(payload: dict[str, Any]) -> pd.DataFrame:
    split_payload = {
        key: value
        for key, value in payload.items()
        if key != _DATAFRAME_MARKER
    }

    if not split_payload.get("data"):
        return pd.DataFrame(columns=split_payload.get("columns") or [])

    return pd.read_json(
        StringIO(json.dumps(split_payload)),
        orient="split",
    )


def _serialize_value(value: Any) -> Any:
    if isinstance(value, pd.DataFrame):
        return _serialize_dataframe(value)

    if isinstance(value, dict):
        return {
            key: _serialize_value(item)
            for key, item in value.items()
        }

    if isinstance(value, list):
        return [_serialize_value(item) for item in value]

    if isinstance(value, tuple):
        return [_serialize_value(item) for item in value]

    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, (np.integer,)):
        return int(value)

    if isinstance(value, (np.floating,)):
        if np.isnan(value):
            return None
        return float(value)

    if isinstance(value, (np.bool_,)):
        return bool(value)

    if isinstance(value, (date, datetime)):
        return value.isoformat()

    return value


def _deserialize_value(value: Any) -> Any:
    if isinstance(value, dict):
        if value.get(_DATAFRAME_MARKER) == _DATAFRAME_TYPE:
            return _deserialize_dataframe(value)

        return {
            key: _deserialize_value(item)
            for key, item in value.items()
        }

    if isinstance(value, list):
        return [_deserialize_value(item) for item in value]

    return value


def _serialize_context(context: dict[str, Any]) -> dict[str, Any]:
    return _serialize_value(context)


def _deserialize_context(payload: dict[str, Any]) -> dict[str, Any]:
    restored = _deserialize_value(payload)
    if not isinstance(restored, dict):
        raise ValueError("Context snapshot must deserialize to a dict.")
    return restored


def build_screening_results(
    pause_seconds=0,
    existing_watchlists=None,
    preset=SCREENING_SNAPSHOT_PRESET,
    limit=None,
):
    watchlists = (
        existing_watchlists
        if existing_watchlists is not None
        else load_watchlists()
    )
    screen_kwargs = {
        "preset": preset,
        "limit": limit,
        "pause_seconds": pause_seconds,
        "existing_watchlists": watchlists,
    }

    usa = screen_us_large(**screen_kwargs)
    norden = screen_nordics(**screen_kwargs)
    obx = screen_obx(**screen_kwargs)

    return {
        "USA": usa,
        "NORDEN": norden,
        "OBX": obx,
        "meta": {
            "USA": _screening_region_meta(usa),
            "NORDEN": _screening_region_meta(norden),
            "OBX": _screening_region_meta(obx),
        },
        "generated_at": _utc_now_iso(),
    }


def _screening_region_meta(region_results):
    if not isinstance(region_results, pd.DataFrame):
        universe_size = 0
    else:
        universe_size = len(region_results)

    return {
        "universe_size": universe_size,
        "is_full_universe": True,
        "display_limit": SCREENING_SNAPSHOT_LIMIT,
        "use_snapshot_wording": False,
    }


def screening_region_meta(screening_results, region_key):
    if not screening_results or not region_key:
        return None

    meta_root = screening_results.get("meta")
    if isinstance(meta_root, dict) and region_key in meta_root:
        return dict(meta_root[region_key])

    region_results = screening_results.get(region_key)
    if not isinstance(region_results, pd.DataFrame) or region_results.empty:
        return None

    universe_size = len(region_results)
    return {
        "universe_size": universe_size,
        "is_full_universe": False,
        "display_limit": min(universe_size, SCREENING_SNAPSHOT_LIMIT),
        "use_snapshot_wording": True,
    }


def save_context_snapshot(
    context: dict[str, Any],
    today: date | None = None,
) -> Path:
    today = today or date.today()
    path = context_snapshot_path()
    payload = {
        "version": CONTEXT_SNAPSHOT_VERSION,
        "model_version": MODEL_VERSION,
        "built_at": _utc_now_iso(),
        "date": today.isoformat(),
        "context": _serialize_context(context),
    }

    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    return path


def _load_context_snapshot_payload() -> dict[str, Any] | None:
    path = context_snapshot_path()

    if not path.exists():
        return None

    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None

    if not isinstance(payload, dict):
        return None

    return payload


def get_context_snapshot_metadata() -> dict[str, Any] | None:
    payload = _load_context_snapshot_payload()
    if payload is None:
        return None

    if payload.get("version") != CONTEXT_SNAPSHOT_VERSION:
        return None

    built_at = _parse_iso_datetime(payload.get("built_at"))
    if built_at is None:
        return None

    return {
        "version": payload.get("version"),
        "model_version": payload.get("model_version"),
        "built_at": payload.get("built_at"),
        "date": payload.get("date"),
    }


def load_context_snapshot(
    max_age_hours: float = 24,
    now: datetime | None = None,
    check_max_age: bool = True,
) -> dict[str, Any] | None:
    payload = _load_context_snapshot_payload()
    if payload is None:
        return None

    if payload.get("version") != CONTEXT_SNAPSHOT_VERSION:
        return None

    built_at = _parse_iso_datetime(payload.get("built_at"))
    if built_at is None:
        return None

    if check_max_age:
        reference = now or datetime.now(timezone.utc)
        if reference.tzinfo is None:
            reference = reference.replace(tzinfo=timezone.utc)

        age_hours = (reference - built_at).total_seconds() / 3600
        if age_hours > max_age_hours:
            return None

    context_payload = payload.get("context")
    if not isinstance(context_payload, dict):
        return None

    try:
        context = _deserialize_context(context_payload)
    except (ValueError, TypeError, json.JSONDecodeError):
        return None

    snapshot_model_version = payload.get("model_version")
    if snapshot_model_version:
        context.setdefault("model_version", snapshot_model_version)
    return context


def reload_context_from_snapshot(
    max_age_hours: float = 24,
    now: datetime | None = None,
) -> dict[str, Any]:
    metadata = get_context_snapshot_metadata()
    if metadata is None:
        return {
            "loaded": False,
            "reason": "missing",
            "context": None,
            "metadata": None,
            "expired": False,
        }

    context = load_context_snapshot(
        max_age_hours=max_age_hours,
        now=now,
        check_max_age=False,
    )
    if context is None:
        return {
            "loaded": False,
            "reason": "invalid",
            "context": None,
            "metadata": metadata,
            "expired": False,
        }

    expired = False
    built_at = _parse_iso_datetime(metadata.get("built_at"))
    if built_at is not None:
        reference = now or datetime.now(timezone.utc)
        if reference.tzinfo is None:
            reference = reference.replace(tzinfo=timezone.utc)
        age_hours = (reference - built_at).total_seconds() / 3600
        expired = age_hours > max_age_hours

    return {
        "loaded": True,
        "reason": "loaded",
        "context": context,
        "metadata": metadata,
        "expired": expired,
    }


def load_or_build_agent_context(
    watchlist,
    portfolio=None,
    pending_orders=None,
    research_ideas=None,
    pause_seconds=1,
    max_age_hours=24,
    now=None,
):
    context = load_context_snapshot(max_age_hours=max_age_hours, now=now)
    if context is not None:
        return context

    return build_agent_context(
        watchlist,
        portfolio=portfolio,
        pending_orders=pending_orders,
        research_ideas=research_ideas,
        pause_seconds=pause_seconds,
    )


def build_agent_context(
    watchlist,
    portfolio=None,
    pending_orders=None,
    research_ideas=None,
    pause_seconds=1,
):
    print("Analyserer watchlist...")

    watchlist_report = analyze_watchlist(
        watchlist,
        pause_seconds=pause_seconds
    )

    portfolio = portfolio or []
    portfolio_report = None

    if len(portfolio) > 0:
        print("Analyserer portefølje...")

        portfolio_report = analyze_portfolio(
            portfolio,
            pause_seconds=pause_seconds
        )

    orders = pending_orders or []
    earnings_summary = build_earnings_summary(
        portfolio=portfolio,
        watchlist=watchlist,
    )
    analyst_summary = build_analyst_summary(
        portfolio=portfolio,
        watchlist=watchlist,
    )
    news_summary = build_news_summary(
        portfolio=portfolio,
        watchlist=watchlist,
    )
    sentiment_summary = build_sentiment_summary(news_summary)
    news_summary = merge_sentiment_into_news_summary(news_summary, sentiment_summary)
    dashboard = build_dashboard(
        watchlist_report=watchlist_report,
        portfolio_report=portfolio_report,
        pending_orders=orders,
        watchlist_symbols=watchlist,
        research_ideas=research_ideas or [],
    )
    dashboard["earnings_summary"] = earnings_summary
    dashboard["analyst_summary"] = analyst_summary
    dashboard["news_summary"] = news_summary
    dashboard["sentiment_summary"] = sentiment_summary
    advisor_output = build_advisor_output(
        portfolio_report=portfolio_report,
        analyst_summary=analyst_summary,
        sentiment_summary=sentiment_summary,
        earnings_summary=earnings_summary,
    )
    dashboard["advisor_output"] = advisor_output
    alerts = build_alerts(
        portfolio_report,
        orders,
        research_ideas or [],
        earnings_summary=earnings_summary,
    )
    advisor_details = build_advisor_details(
        advisor_output,
        portfolio_report,
        analyst_summary=analyst_summary,
        sentiment_summary=sentiment_summary,
        earnings_summary=earnings_summary,
        alerts=alerts,
    )
    daily_flow = build_daily_flow(
        watchlist_report=watchlist_report,
        portfolio_report=portfolio_report,
        dashboard=dashboard,
        pending_orders=orders,
        alerts=alerts,
        portfolio=portfolio,
    )
    watchlist_advisor_output = build_watchlist_advisor(
        watchlist_report=watchlist_report,
        portfolio_report=portfolio_report,
        portfolio=portfolio,
        analyst_summary=analyst_summary,
        sentiment_summary=sentiment_summary,
        earnings_summary=earnings_summary,
        snapshot_changes=dashboard.get("changes_since_last_snapshot"),
    )
    screening_results = build_screening_results(
        pause_seconds=pause_seconds,
        existing_watchlists=load_watchlists(),
    )

    context = {
        "model_version": MODEL_VERSION,
        "watchlist": watchlist,
        "watchlist_report": watchlist_report,
        "portfolio_report": portfolio_report,
        "dashboard": dashboard,
        "daily_flow": daily_flow,
        "earnings_summary": earnings_summary,
        "analyst_summary": analyst_summary,
        "news_summary": news_summary,
        "sentiment_summary": sentiment_summary,
        "advisor_output": advisor_output,
        "advisor_details": advisor_details,
        "watchlist_advisor_output": watchlist_advisor_output,
        "alerts": alerts,
        "screening_results": screening_results,
    }
    context["recommendations"] = build_recommendations(context)
    context["daily_briefing"] = build_daily_briefing(
        context,
        recommendations=context["recommendations"],
    )

    return context


def resolve_portfolio_report(context, portfolio):
    report = ensure_portfolio_report(
        context.get("portfolio_report"),
        portfolio,
    )

    if report is not None:
        context["portfolio_report"] = report
        dashboard = context.setdefault("dashboard", {})
        dashboard["portfolio_summary"] = summarize_portfolio(report)
        dashboard["portfolio_risk"] = build_portfolio_risk(report)

    return report
