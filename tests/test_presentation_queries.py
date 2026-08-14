from datetime import date, datetime, timezone

import pandas as pd
import pytest

from src.presentation_queries import PresentationQueries
from src.recommendation_contract import build_contract_fields


NOW = datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc)


def _context_result(*, expired=False, loaded=True, reason="loaded"):
    context = {
        "model_version": "test-model-v1",
        "watchlist_report": pd.DataFrame(
            [
                {
                    "ticker": "NVDA",
                    "company_name": "NVIDIA Corporation",
                    "score": 78,
                    "anbefaling": "KJØP / ØK",
                    "kurs": 180,
                    "trend_regime": "STERK OPPTREND",
                    "benchmark": "SPY",
                    "relative_strength_20d": 8.2,
                    "technical_score": 80,
                    "fundamental_score": 70,
                    "fundamental_history_score": 60,
                    "begrunnelse": ["Sterk trend", "God kvalitet"],
                    "fundamental_reasons": ["Vekst i inntjening"],
                },
                {
                    "ticker": "MSFT",
                    "company_name": "Microsoft Corporation",
                    "score": 65,
                    "anbefaling": "HOLD / OBSERVER",
                    "kurs": float("nan"),
                    "trend_regime": "MODERAT OPPTREND",
                    "benchmark": "SPY",
                    "relative_strength_20d": -1.5,
                    "begrunnelse": ["Kurs over SMA50"],
                },
            ]
        ),
        "portfolio_report": pd.DataFrame(
            [
                {
                    "ticker": "NVDA",
                    "current_price": 180,
                    "unrealized_gain_pct": 55.2,
                    "anbefaling": "HOLD / OBSERVER",
                    "portefølje_råd": "BEHOLD",
                    "stop_loss": 150,
                    "trailing_stop_loss": 165,
                    "begrunnelse": "Beskytt gevinst",
                }
            ]
        ),
        "opportunity_advisor": {
            "items": [
                {
                    "ticker": "GOOGL",
                    "company_name": "Alphabet Inc.",
                    "score": 72,
                    "recommendation": "KJØP / ØK",
                }
            ]
        },
        "daily_briefing": {
            "critical_items": [
                {
                    "ticker": "NVDA",
                    "title": "Vurder gevinstsikring",
                    "priority": "high",
                    "recommendation": "BEHOLD",
                }
            ]
        },
        "recommendations": {
            "contract_version": "1.0",
            "actions": [
                {
                    "ticker": "NVDA",
                    "decision": build_contract_fields(
                        ticker="NVDA",
                        category="Portefølje",
                        rule="trailing_stop_near",
                        reason="Beskytt gevinst",
                        confidence="høy",
                        stop_level=165,
                    ),
                }
            ],
        },
        "watchlist": ["NVDA", "MSFT"],
        "earnings_summary": {"items": [{"ticker": "NVDA", "event_label": "Q2-rapport"}]},
        "news_summary": {"items": [{"ticker": "NVDA", "headline": "Ny produktlansering", "url": "https://example.com/news"}]},
        "analyst_summary": {
            "items": [
                {"ticker": "NVDA", "currency": "USD", "recommendation_key": "buy", "analyst_count": 42, "target_mean": 220, "upside_pct": 22.2},
                {"ticker": "MSFT", "currency": "USD"},
            ]
        },
        "dashboard": {
            "changes_since_last_snapshot": {
                "recommendation_changed": pd.DataFrame([
                    {"ticker": "MSFT", "previous_recommendation": "KJØP / ØK", "current_recommendation": "HOLD / OBSERVER", "score_change": -6}
                ]),
                "large_score_changes": pd.DataFrame(),
            }
        },
    }
    return {
        "loaded": loaded,
        "reason": reason,
        "context": context if loaded else None,
        "metadata": {
            "model_version": "test-model-v1",
            "built_at": "2026-08-08T08:00:00+00:00",
            "date": "2026-08-08",
        },
        "expired": expired,
    }


def _queries(context_result=None):
    result = context_result or _context_result()
    return PresentationQueries(
        context_loader=lambda **_kwargs: result,
        portfolio_loader=lambda _default=None: [
            {"ticker": "NVDA", "buy_price": 116, "shares": 10}
        ],
        watchlists_loader=lambda: {
            "USA": ["NVDA", "MSFT"],
            "Alle": ["MSFT", "NVDA"],
        },
        company_name_loader=lambda ticker: {
            "NVDA": "NVIDIA Corporation",
            "MSFT": "Microsoft Corporation",
            "GOOGL": "Alphabet Inc.",
        }.get(ticker, ticker),
        refresh_state_loader=lambda: {
            "last_status": "success",
            "last_successful_date": date.today().isoformat(),
            "last_finished_at": "2026-08-08T08:00:00+00:00",
            "last_error_count": 0,
        },
        chat_handler=lambda question, context: f"{question}: {context['model_version']}",
        now=lambda: NOW,
        snapshots_loader=lambda: pd.DataFrame([
            {"date": "2026-08-07", "ticker": "NVDA"},
            {"date": "2026-08-08", "ticker": "NVDA"},
        ]),
        discovery_journal_loader=lambda: pd.DataFrame([
            {"signal_date": "2026-08-08", "ticker": "GOOGL"},
        ]),
        decision_journal_loader=lambda: [
            {"signal_date": "2026-08-08", "entry_id": "one"},
            {"signal_date": "2026-08-08", "entry_id": "two"},
        ],
        decision_outcomes_loader=lambda: [
            {"entry_id": "one", "status": "partial"},
            {"entry_id": "two", "status": "pending"},
        ],
    )


def test_today_is_small_normalized_contract():
    result = _queries().today()

    assert set(result) == {"meta", "attention", "owned", "watchlist", "candidates"}
    assert result["meta"]["status"] == "fresh"
    assert result["owned"][0]["ticker"] == "NVDA"
    assert result["owned"][0]["average_cost"] == 116.0
    assert result["owned"][0]["requires_attention"] is True
    assert result["owned"][0]["action_label"] == "BEHOLD"
    assert result["owned"][0]["stop_level"] == 165.0
    assert result["owned"][0]["stop_kind"] == "trailing stop"
    assert result["owned"][0]["distance_to_stop_pct"] == 9.09
    assert result["owned"][0]["gain_pct"] == 55.2
    assert result["owned"][0]["currency"] == "USD"
    assert result["owned"][0]["decision"]["action_code"] == "protect_position"
    assert result["owned"][0]["decision"]["stop_level"] == 165.0
    assert result["watchlist"][0]["ticker"] == "MSFT"
    assert result["watchlist"][0]["current_price"] is None
    assert result["watchlist"][0]["relative_strength_pct"] == -1.5
    assert result["watchlist"][0]["benchmark"] == "SPY"
    assert result["watchlist"][0]["changed_today"] is True
    assert result["watchlist"][0]["change_label"] == (
        "Endret fra KJØP / ØK til HOLD / OBSERVER"
    )
    assert result["candidates"][0]["ticker"] == "GOOGL"


def test_moved_position_keeps_snapshot_analysis_until_next_refresh():
    result = _context_result()
    result["context"]["portfolio_report"] = pd.DataFrame(
        [
            {
                "ticker": "KMAR.OL",
                "score": 93,
                "anbefaling": "KJØP / ØK",
                "trend_regime": "STERK OPPTREND",
                "relative_strength_20d": 8.14,
            }
        ]
    )
    queries = PresentationQueries(
        context_loader=lambda **_kwargs: result,
        portfolio_loader=lambda _default=None: [],
        watchlists_loader=lambda: {"OBX": ["KMAR.OL"], "Alle": ["KMAR.OL"]},
        company_name_loader=lambda _ticker: "KMC Properties",
        now=lambda: NOW,
    )

    card = queries.today()["watchlist"][0]

    assert card["ticker"] == "KMAR.OL"
    assert card["recommendation"] == "KJØP / ØK"
    assert card["score"] == 93.0
    assert card["trend_regime"] == "STERK OPPTREND"
    assert card["relative_strength_pct"] == 8.14


def test_identity_is_consistent_across_resources():
    queries = _queries()

    today_name = queries.today()["owned"][0]["company_name"]
    today_item = queries.today()["owned"][0]
    position_item = queries.positions()["positions"][0]
    search_name = queries.search("nvidia")["results"][0]["company_name"]
    company = queries.company_context("nvda")

    assert {
        today_name,
        position_item["company_name"],
        search_name,
        company["company_name"],
    } == {
        "NVIDIA Corporation"
    }
    assert {
        today_item["recommendation"],
        position_item["recommendation"],
        company["recommendation"],
    } == {"KJØP / ØK"}
    assert company["meta"]["model_version"] == "test-model-v1"
    assert company["owned"] is True
    assert company["action_label"] == "BEHOLD"
    assert company["action_reason"] == "Beskytt gevinst"
    assert company["decision"]["action_code"] == "protect_position"
    assert company["technical_score"] == 80.0
    assert company["fundamental_reasons"] == ["Vekst i inntjening"]
    assert company["analyst_consensus"] == "buy"
    assert company["next_event"]["event_label"] == "Q2-rapport"
    assert company["news"][0]["headline"] == "Ny produktlansering"


def test_non_owned_company_has_no_portfolio_action():
    company = _queries().company_context("MSFT")

    assert company["owned"] is False
    assert company["action_label"] is None
    assert company["action_reason"] is None
    assert company["recommendation"] == "HOLD / OBSERVER"


def test_stale_and_missing_context_are_explicit():
    stale = _queries(_context_result(expired=True)).today()
    missing = _queries(
        _context_result(loaded=False, reason="missing")
    ).today()

    assert stale["meta"]["status"] == "stale"
    assert stale["meta"]["message"] == "Analysedata er eldre enn 24 timer."
    assert missing["meta"]["status"] == "missing"
    assert missing["owned"][0]["ticker"] == "NVDA"
    assert missing["owned"][0]["stop_level"] is None
    assert missing["owned"][0]["distance_to_stop_pct"] is None
    assert missing["owned"][0]["currency"] == "USD"
    assert missing["watchlist"][0]["ticker"] == "MSFT"
    assert missing["watchlist"][0]["relative_strength_pct"] is None
    assert missing["watchlist"][0]["changed_today"] is False


def test_search_requires_a_match_and_limits_results():
    queries = _queries()

    assert queries.search("micro")["results"][0]["ticker"] == "MSFT"
    assert queries.search("unknown")["results"] == []
    assert len(queries.search("m", limit=1)["results"]) == 1


def test_chat_uses_existing_agent_and_rejects_missing_context():
    assert _queries().chat("Oppsummer")["answer"] == "Oppsummer: test-model-v1"

    contextual = _queries().chat(
        "Hva bør jeg følge med på?",
        view="detail",
        ticker="NVDA",
        company_name="NVIDIA Corporation",
    )["answer"]
    assert "Spørsmålet gjelder NVDA (NVIDIA Corporation)" in contextual

    missing = _queries(_context_result(loaded=False, reason="missing"))
    with pytest.raises(LookupError, match="Daily Refresh"):
        missing.chat("Oppsummer")


def test_model_and_refresh_status_share_environment(monkeypatch):
    monkeypatch.setenv("STOCK_AGENT_ENV", "test")
    result = _queries().model_status()

    assert result["meta"]["environment"] == "test"
    assert result["meta"]["model_version"] == "test-model-v1"
    assert result["refresh"]["environment"] == "test"
    assert result["refresh"]["last_error_count"] == 0


def test_positions_deduplicate_repeated_ticker_rows():
    queries = _queries()
    queries._portfolio_loader = lambda _default=None: [
        {"ticker": "NVDA", "buy_price": 100},
        {"ticker": "NVDA", "buy_price": 116},
    ]

    result = queries.positions()["positions"]

    assert [row["ticker"] for row in result] == ["NVDA"]
    assert result[0]["average_cost"] == 116.0


def test_explore_groups_existing_classifications():
    result = _queries().explore()

    assert [stock["ticker"] for stock in result["watchlist_ranking"]] == ["MSFT"]
    assert {profile["key"] for profile in result["profiles"]} == {
        "QUALITY_COMPOUNDER", "COMPOUNDER", "MOMENTUM", "CYCLICAL", "WEAK/AVOID", "UNKNOWN"
    }
    assert sum(profile["count"] for profile in result["profiles"]) == 1
    assert next(profile for profile in result["profiles"] if profile["key"] == "UNKNOWN")["label"] == "Øvrige"


def test_current_candidates_exclude_owned_and_watchlist_without_stale_fallback():
    result = _context_result()
    result["context"]["opportunity_advisor"] = {
        "items": [
            {"ticker": "NVDA", "score": 90},
            {"ticker": "MSFT", "score": 85},
        ]
    }
    queries = _queries(result)

    assert queries.today()["candidates"] == []
    explore = queries.explore()
    assert explore["candidates"] == []
    assert explore["candidate_source"]["kind"] == "current_snapshot"


def test_model_data_reports_observed_status_without_alpha_claim():
    result = _queries().model_data()

    assert result["snapshots"] == {
        "rows": 2,
        "dates": 2,
        "latest_date": "2026-08-08",
    }
    assert result["discovery_journal"]["cohorts"] == 1
    assert result["discovery_journal"]["status"] == "Prospektiv validering pågår"
    assert result["decision_journal"]["entries"] == 2
    assert result["decision_journal"]["days"] == 1
    assert result["decision_journal"]["latest_signal_date"] == "2026-08-08"
    assert result["decision_journal"]["outcomes"] == 2
    assert result["decision_journal"]["partial"] == 1
    assert result["decision_journal"]["pending"] == 1
    assert result["decision_journal"]["report"]["status"] == "collecting"
    assert result["decision_journal"]["report"]["complete_40d"] == 0
    assert result["decision_journal"]["report"]["horizons"][0]["days"] == 5
    assert result["decision_journal"]["report"]["horizons"][0]["statistics"] is None
    assert result["backtest_validation"]["status"] == "BLOCKED"
    assert any(
        check["check_id"] == "rolling_walk_forward"
        for check in result["backtest_validation"]["checks"]
    )
