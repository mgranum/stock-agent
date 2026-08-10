from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from src.agent import ask_agent
from src.backtest_validation import build_backtest_validation_report
from src.company_names import get_company_name
from src.company_detail_query import normalize_ticker
from src.config import load_watchlists
from src.context import reload_context_from_snapshot
from src.daily_refresh import format_refresh_panel_status, load_refresh_state
from src.discovery_validation import load_discovery_journal
from src.decision_journal import load_decision_journal
from src.environment import get_environment
from src.model_version import MODEL_VERSION
from src.model_backtest import load_snapshots
from src.storage import load_portfolio
from src.strategy_classification import STRATEGY_TYPES, add_strategy_types


@dataclass(frozen=True)
class ContextState:
    status: str
    context: dict[str, Any]
    metadata: dict[str, Any]
    message: str | None


def _records(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, pd.DataFrame):
        cleaned = value.astype(object).where(pd.notnull(value), None)
        return cleaned.to_dict(orient="records")
    if isinstance(value, list):
        return [dict(item) for item in value if isinstance(item, dict)]
    return []


def _finite_number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(number):
        return None
    return round(number, 4)


def _text(row: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _texts(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if value is not None and str(value).strip():
        return [str(value).strip()]
    return []


def _ticker(row: dict[str, Any]) -> str | None:
    value = _text(row, "ticker", "symbol")
    return value.upper() if value else None


def _currency_for(ticker: str, explicit: str | None = None) -> str:
    if explicit:
        return explicit.upper()
    if ticker.endswith(".OL"):
        return "NOK"
    if ticker.endswith(".ST"):
        return "SEK"
    if ticker.endswith(".CO"):
        return "DKK"
    if ticker.endswith(".HE"):
        return "EUR"
    return "USD"


def _decisions_by_ticker(context: dict[str, Any]) -> dict[str, dict[str, Any]]:
    decisions = {}
    recommendations = context.get("recommendations") or {}
    items = recommendations.get("decisions") or recommendations.get("actions") or []
    for item in items:
        decision = item.get("decision")
        if not isinstance(decision, dict):
            continue
        ticker = str(decision.get("ticker") or "").strip().upper()
        if ticker and ticker not in decisions:
            decisions[ticker] = decision
    return decisions


class PresentationQueries:
    def __init__(
        self,
        context_loader: Callable = reload_context_from_snapshot,
        portfolio_loader: Callable = load_portfolio,
        watchlists_loader: Callable = load_watchlists,
        company_name_loader: Callable = get_company_name,
        refresh_state_loader: Callable = load_refresh_state,
        chat_handler: Callable = ask_agent,
        now: Callable = lambda: datetime.now(timezone.utc),
        snapshots_loader: Callable = load_snapshots,
        discovery_journal_loader: Callable = load_discovery_journal,
        decision_journal_loader: Callable = load_decision_journal,
        backtest_validation_builder: Callable = build_backtest_validation_report,
    ):
        self._context_loader = context_loader
        self._portfolio_loader = portfolio_loader
        self._watchlists_loader = watchlists_loader
        self._company_name_loader = company_name_loader
        self._refresh_state_loader = refresh_state_loader
        self._chat_handler = chat_handler
        self._now = now
        self._snapshots_loader = snapshots_loader
        self._discovery_journal_loader = discovery_journal_loader
        self._decision_journal_loader = decision_journal_loader
        self._backtest_validation_builder = backtest_validation_builder

    def _state(self) -> ContextState:
        loaded = self._context_loader(max_age_hours=24, now=self._now())
        metadata = dict(loaded.get("metadata") or {})
        context = loaded.get("context")
        if loaded.get("loaded") and isinstance(context, dict):
            if loaded.get("expired"):
                return ContextState(
                    status="stale",
                    context=context,
                    metadata=metadata,
                    message="Analysedata er eldre enn 24 timer.",
                )
            return ContextState("fresh", context, metadata, None)

        reason = loaded.get("reason") or "missing"
        message = (
            "Context-snapshot mangler. Kjør Daily Refresh."
            if reason == "missing"
            else "Context-snapshot er ugyldig. Kjør Daily Refresh."
        )
        return ContextState(reason, {}, metadata, message)

    def _meta(self, state: ContextState) -> dict[str, Any]:
        card = {
            "status": state.status,
            "environment": get_environment(),
            "model_version": (
                state.context.get("model_version")
                or state.metadata.get("model_version")
                or MODEL_VERSION
            ),
            "built_at": state.metadata.get("built_at"),
            "snapshot_date": state.metadata.get("date"),
            "message": state.message,
        }
        return card

    def _sources(self, state: ContextState):
        portfolio = self._portfolio_loader([]) or []
        watchlists = self._watchlists_loader() or {}
        watchlist_rows = _records(state.context.get("watchlist_report"))
        portfolio_rows = _records(state.context.get("portfolio_report"))
        candidates = _records(
            (state.context.get("opportunity_advisor") or {}).get("items")
        ) or _records(state.context.get("discovery_candidates"))
        return portfolio, watchlists, watchlist_rows, portfolio_rows, candidates

    def _identity_names(self, *row_sets: list[dict[str, Any]]) -> dict[str, str]:
        names = {}
        for rows in row_sets:
            for row in rows:
                ticker = _ticker(row)
                name = _text(row, "company_name", "name")
                if ticker and name:
                    names[ticker] = name
        return names

    def _name(self, ticker: str, names: dict[str, str]) -> str:
        if ticker in names:
            return names[ticker]
        return self._company_name_loader(ticker) or ticker

    def _stock_card(
        self,
        row: dict[str, Any],
        *,
        names: dict[str, str],
        owned: bool = False,
        average_cost: float | None = None,
        requires_attention: bool = False,
        currency: str | None = None,
        decision: dict[str, Any] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        ticker = _ticker(row)
        if not ticker:
            return None
        card = {
            "ticker": ticker,
            "company_name": self._name(ticker, names),
            "recommendation": _text(
                row, "recommendation", "anbefaling", "portefølje_råd", "action"
            ),
            "score": _finite_number(row.get("score")),
            "current_price": _finite_number(
                row.get("current_price", row.get("kurs"))
            ),
            "change_pct": _finite_number(
                row.get("change_pct", row.get("unrealized_gain_pct"))
            ),
            "trend_regime": _text(row, "trend_regime"),
            "owned": owned,
            "average_cost": _finite_number(average_cost),
            "requires_attention": requires_attention,
            "currency": _currency_for(ticker, currency),
            "rationale": None,
            "action_label": None,
            "stop_level": None,
            "stop_kind": None,
            "distance_to_stop_pct": None,
            "gain_pct": None,
            "benchmark": None,
            "relative_strength_pct": None,
            "changed_today": False,
            "change_label": None,
            "decision": decision,
            **(extra or {}),
        }
        if decision:
            label = _text(decision, "label")
            reasons = _texts(decision.get("reasons"))
            if decision.get("scope") == "portfolio" and label:
                card["action_label"] = label
            elif label:
                card["recommendation"] = label
            if reasons:
                card["rationale"] = reasons[0]
        return card

    def _documented_changes(self, state: ContextState) -> dict[str, str]:
        changes = (state.context.get("dashboard") or {}).get(
            "changes_since_last_snapshot"
        ) or {}
        labels: dict[str, str] = {}
        for key in ("recommendation_changed", "large_score_changes"):
            for row in _records(changes.get(key)):
                ticker = _ticker(row)
                if not ticker:
                    continue
                previous = _text(row, "previous_recommendation")
                current = _text(row, "current_recommendation")
                if previous and current and previous != current:
                    labels[ticker] = f"Endret fra {previous} til {current}"
                else:
                    score_change = _finite_number(row.get("score_change"))
                    labels[ticker] = (
                        f"Score endret {score_change:+g}"
                        if score_change is not None
                        else "Endret siden sist"
                    )
        return labels

    def _attention(self, state: ContextState) -> list[dict[str, Any]]:
        briefing = state.context.get("daily_briefing") or {}
        keys = (
            "critical_items",
            "change_items",
            "important_items",
            "portfolio_items",
            "earnings_items",
        )
        items = []
        seen = set()
        for key in keys:
            for row in _records(briefing.get(key)):
                ticker = _ticker(row)
                title = _text(row, "title", "headline", "summary", "action")
                detail = _text(row, "detail", "reason", "message", "text")
                if not title:
                    title = detail or (f"Oppfølging av {ticker}" if ticker else None)
                if not title:
                    continue
                identity = (ticker, title)
                if identity in seen:
                    continue
                seen.add(identity)
                items.append(
                    {
                        "ticker": ticker,
                        "title": title,
                        "detail": detail if detail != title else None,
                        "recommendation": _text(
                            row, "recommendation", "anbefaling", "action"
                        ),
                        "priority": _text(row, "priority", "severity"),
                        "source": _text(row, "source") or key,
                    }
                )
        return items

    def company_context(self, ticker: str) -> dict[str, Any]:
        state = self._state()
        portfolio, _watchlists, watch_rows, portfolio_rows, candidates = self._sources(state)
        symbol = str(ticker).strip().upper()
        decisions = _decisions_by_ticker(state.context)
        owned_tickers = {_ticker(row) for row in portfolio if _ticker(row)}
        final_decision = decisions.get(symbol)
        portfolio_analysis = next(
            (row for row in portfolio_rows if _ticker(row) == symbol),
            {},
        )
        rows = watch_rows + portfolio_rows + candidates + portfolio
        names = self._identity_names(rows)
        analysis = next(
            (row for row in watch_rows if _ticker(row) == symbol),
            None,
        ) or next(
            (row for row in portfolio_rows if _ticker(row) == symbol),
            None,
        ) or next(
            (row for row in candidates if _ticker(row) == symbol),
            {"ticker": symbol},
        )
        card = self._stock_card(analysis, names=names)
        analyst = next(
            (
                row
                for row in _records((state.context.get("analyst_summary") or {}).get("items"))
                if _ticker(row) == symbol
            ),
            {},
        )
        earnings = next(
            (
                row
                for row in _records((state.context.get("earnings_summary") or {}).get("items"))
                if _ticker(row) == symbol
            ),
            None,
        )
        articles = [
            row
            for row in _records((state.context.get("news_summary") or {}).get("items"))
            if _ticker(row) == symbol
        ][:5]
        return {
            "meta": self._meta(state),
            "company_name": card["company_name"] if card else symbol,
            "recommendation": card["recommendation"] if card else None,
            "owned": symbol in owned_tickers,
            "action_label": (
                _text(final_decision or {}, "label")
                or _text(portfolio_analysis, "portefølje_råd")
                if symbol in owned_tickers
                else None
            ),
            "action_reason": (
                (
                    _texts((final_decision or {}).get("reasons"))
                    or [_text(portfolio_analysis, "begrunnelse")]
                )[0]
                if symbol in owned_tickers
                else None
            ),
            "decision": final_decision,
            "score": card["score"] if card else None,
            "trend_regime": _text(analysis, "trend_regime"),
            "reasoning": _texts(analysis.get("begrunnelse")),
            "technical_score": _finite_number(analysis.get("technical_score")),
            "fundamental_score": _finite_number(analysis.get("fundamental_score")),
            "fundamental_label": _text(analysis, "fundamental_label"),
            "fundamental_reasons": _texts(analysis.get("fundamental_reasons")),
            "history_score": _finite_number(analysis.get("fundamental_history_score")),
            "history_label": _text(analysis, "fundamental_history_label"),
            "analyst_consensus": _text(analyst, "recommendation_key"),
            "analyst_count": analyst.get("analyst_count"),
            "target_mean": _finite_number(analyst.get("target_mean")),
            "upside_pct": _finite_number(analyst.get("upside_pct")),
            "next_event": earnings,
            "news": articles,
        }

    def today(self) -> dict[str, Any]:
        state = self._state()
        portfolio, watchlists, watch_rows, portfolio_rows, candidates = self._sources(state)
        portfolio_by_ticker = {_ticker(row): row for row in portfolio_rows if _ticker(row)}
        watch_by_ticker = {_ticker(row): row for row in watch_rows if _ticker(row)}
        raw_positions = {_ticker(row): row for row in portfolio if _ticker(row)}
        names = self._identity_names(
            portfolio, watch_rows, portfolio_rows, candidates
        )
        attention = self._attention(state)
        attention_tickers = {item["ticker"] for item in attention if item["ticker"]}
        changes = self._documented_changes(state)
        decisions = _decisions_by_ticker(state.context)
        analyst_rows = _records(
            (state.context.get("analyst_summary") or {}).get("items")
        )
        currencies = {
            _ticker(row): _text(row, "currency")
            for row in analyst_rows
            if _ticker(row)
        }

        owned = []
        for ticker, position in raw_positions.items():
            analysis = {
                **(portfolio_by_ticker.get(ticker) or {}),
                **(watch_by_ticker.get(ticker) or {}),
            } or position
            card = self._stock_card(
                analysis,
                names=names,
                owned=True,
                average_cost=position.get("buy_price", position.get("average_cost")),
                requires_attention=ticker in attention_tickers,
                currency=currencies.get(ticker),
                decision=decisions.get(ticker),
                extra=self._owned_card_details(
                    analysis,
                    portfolio_by_ticker.get(ticker) or {},
                    changes.get(ticker),
                ),
            )
            if card:
                owned.append(card)

        all_watchlist = list(dict.fromkeys(watchlists.get("Alle") or []))
        watchlist = []
        for ticker in all_watchlist:
            ticker = str(ticker).upper()
            if ticker in raw_positions:
                continue
            # A ticker can move from portfolio to watchlist between Daily
            # Refresh runs. Reuse its existing snapshot analysis so the UI
            # does not temporarily lose recommendation, score and trend.
            analysis = {
                **(portfolio_by_ticker.get(ticker) or {}),
                **(watch_by_ticker.get(ticker) or {}),
            } or {"ticker": ticker}
            card = self._stock_card(
                analysis,
                names=names,
                requires_attention=ticker in attention_tickers,
                currency=currencies.get(ticker),
                decision=decisions.get(ticker),
                extra=self._watch_card_details(
                    analysis,
                    changes.get(ticker),
                ),
            )
            if card:
                watchlist.append(card)

        candidate_cards = [
            card
            for row in candidates[:3]
            if (
                card := self._stock_card(
                    row,
                    names=names,
                    decision=decisions.get(_ticker(row) or ""),
                )
            ) is not None
        ]
        return {
            "meta": self._meta(state),
            "attention": attention,
            "owned": owned,
            "watchlist": watchlist,
            "candidates": candidate_cards,
        }

    def _owned_card_details(
        self,
        analysis: dict[str, Any],
        portfolio_row: dict[str, Any],
        change_label: str | None,
    ) -> dict[str, Any]:
        current = _finite_number(
            portfolio_row.get("current_price", analysis.get("kurs"))
        )
        trailing = _finite_number(portfolio_row.get("trailing_stop_loss"))
        ordinary = _finite_number(portfolio_row.get("stop_loss"))
        stop_level = trailing if trailing is not None else ordinary
        distance = None
        if current is not None and stop_level not in (None, 0):
            distance = round((current / stop_level - 1) * 100, 2)
        rationale = _text(portfolio_row, "begrunnelse")
        if not rationale:
            rationale = _texts(analysis.get("begrunnelse"))[0] if _texts(analysis.get("begrunnelse")) else None
        return {
            "rationale": rationale,
            "action_label": _text(portfolio_row, "portefølje_råd"),
            "stop_level": stop_level,
            "stop_kind": "trailing stop" if trailing is not None else ("stop-loss" if ordinary is not None else None),
            "distance_to_stop_pct": distance,
            "gain_pct": _finite_number(portfolio_row.get("unrealized_gain_pct")),
            "benchmark": _text(analysis, "benchmark"),
            "relative_strength_pct": _finite_number(analysis.get("relative_strength_20d")),
            "changed_today": change_label is not None,
            "change_label": change_label,
        }

    def _watch_card_details(
        self,
        row: dict[str, Any],
        change_label: str | None,
    ) -> dict[str, Any]:
        reasons = _texts(row.get("begrunnelse"))
        return {
            "rationale": change_label or (reasons[0] if reasons else None),
            "benchmark": _text(row, "benchmark"),
            "relative_strength_pct": _finite_number(row.get("relative_strength_20d")),
            "changed_today": change_label is not None,
            "change_label": change_label,
        }

    def explore(self) -> dict[str, Any]:
        state = self._state()
        portfolio, _watchlists, watch_rows, portfolio_rows, candidates = self._sources(state)
        owned = {_ticker(row) for row in portfolio if _ticker(row)}
        watchlist_rows = [row for row in watch_rows if _ticker(row) not in owned]
        names = self._identity_names(portfolio, watch_rows, portfolio_rows, candidates)
        decisions = _decisions_by_ticker(state.context)
        ranking = [
            card
            for row in sorted(
                watchlist_rows,
                key=lambda item: _finite_number(item.get("score")) or -1,
                reverse=True,
            )
            if (
                card := self._stock_card(
                    row,
                    names=names,
                    owned=_ticker(row) in owned,
                    decision=decisions.get(_ticker(row) or ""),
                    extra={
                        **self._watch_card_details(row, None),
                        "strategy_type": _text(row, "strategy_type"),
                    },
                )
            ) is not None
        ]
        discovery_rows = _records(state.context.get("discovery_candidates"))
        candidate_rows = candidates or [
            row for row in discovery_rows if not bool(row.get("in_watchlist"))
        ]
        candidate_source = {
            "kind": "current_snapshot" if candidate_rows else "none",
            "label": "Siste screening-snapshot",
            "date": (state.context.get("screening_results") or {}).get("generated_at"),
        }
        if not candidate_rows:
            journal = self._discovery_journal_loader()
            if isinstance(journal, pd.DataFrame) and not journal.empty and "signal_date" in journal:
                latest_date = sorted(str(value) for value in journal["signal_date"].dropna().unique())[-1]
                candidate_rows = [
                    row for row in _records(journal[journal["signal_date"].astype(str) == latest_date])
                    if not bool(row.get("in_watchlist"))
                ]
                candidate_source = {
                    "kind": "discovery_journal",
                    "label": "Siste fullførte screening",
                    "date": latest_date,
                }
        candidate_cards = [
            card
            for row in candidate_rows
            if (
                card := self._stock_card(
                    row,
                    names=names,
                    decision=decisions.get(_ticker(row) or ""),
                )
            ) is not None
        ]
        classified = add_strategy_types(pd.DataFrame(watchlist_rows)) if watchlist_rows else pd.DataFrame()
        profiles = []
        labels = {
            "QUALITY_COMPOUNDER": "Kvalitetsselskaper",
            "COMPOUNDER": "Kvalitet med trend",
            "MOMENTUM": "Vekst med trend",
            "CYCLICAL": "Sykliske",
            "WEAK/AVOID": "Svak / unngå",
            "UNKNOWN": "Øvrige",
        }
        for strategy_type in STRATEGY_TYPES:
            rows = (
                classified[classified["strategy_type"] == strategy_type]
                .sort_values("score", ascending=False)
                .to_dict(orient="records")
                if not classified.empty
                else []
            )
            profiles.append(
                {
                    "key": strategy_type,
                    "label": labels[strategy_type],
                    "count": len(rows),
                    "stocks": [
                        card
                        for row in rows
                        if (card := self._stock_card(
                            row,
                            names=names,
                            owned=_ticker(row) in owned,
                            decision=decisions.get(_ticker(row) or ""),
                            extra={
                                **self._watch_card_details(row, None),
                                "strategy_type": strategy_type,
                            },
                        )) is not None
                    ],
                }
            )
        return {
            "meta": self._meta(state),
            "watchlist_ranking": ranking,
            "candidates": candidate_cards,
            "profiles": profiles,
            "research_ideas": state.context.get("research_ideas")
            or (state.context.get("dashboard") or {}).get("research_ideas")
            or {},
            "candidate_source": candidate_source,
        }

    def positions(self) -> dict[str, Any]:
        state = self._state()
        portfolio, _watchlists, watch_rows, portfolio_rows, candidates = self._sources(state)
        report_by_ticker = {_ticker(row): row for row in portfolio_rows if _ticker(row)}
        watch_by_ticker = {_ticker(row): row for row in watch_rows if _ticker(row)}
        names = self._identity_names(portfolio, watch_rows, portfolio_rows, candidates)
        positions = []
        unique_positions = {
            _ticker(raw): raw for raw in portfolio if _ticker(raw)
        }
        for raw in unique_positions.values():
            ticker = _ticker(raw)
            if not ticker:
                continue
            report = report_by_ticker.get(ticker) or {}
            analysis = watch_by_ticker.get(ticker) or report
            positions.append(
                {
                    "ticker": ticker,
                    "company_name": self._name(ticker, names),
                    "average_cost": _finite_number(
                        raw.get("buy_price", raw.get("average_cost"))
                    ),
                    "shares": _finite_number(raw.get("shares")),
                    "current_price": _finite_number(
                        report.get("current_price", report.get("kurs"))
                    ),
                    "recommendation": _text(
                        analysis, "anbefaling", "recommendation"
                    ),
                    "portfolio_action": _text(report, "portefølje_råd"),
                    "stop_loss": _finite_number(report.get("stop_loss")),
                    "trailing_stop_loss": _finite_number(
                        report.get("trailing_stop_loss")
                    ),
                }
            )
        return {"meta": self._meta(state), "positions": positions}

    def watchlists(self) -> dict[str, Any]:
        state = self._state()
        groups = []
        for name, tickers in (self._watchlists_loader() or {}).items():
            groups.append(
                {
                    "name": str(name),
                    "tickers": [str(ticker).upper() for ticker in tickers],
                    "editable": name != "Alle",
                }
            )
        return {"meta": self._meta(state), "watchlists": groups}

    def search(self, query: str, limit: int = 20) -> dict[str, Any]:
        state = self._state()
        portfolio, watchlists, watch_rows, portfolio_rows, candidates = self._sources(state)
        names = self._identity_names(portfolio, watch_rows, portfolio_rows, candidates)
        owned = {_ticker(row) for row in portfolio if _ticker(row)}
        memberships: dict[str, list[str]] = {}
        for name, tickers in watchlists.items():
            if name == "Alle":
                continue
            for ticker in tickers:
                memberships.setdefault(str(ticker).upper(), []).append(str(name))
        tickers = set(names) | owned | set(memberships)
        needle = str(query or "").strip().casefold()
        results = []
        if needle:
            for ticker in sorted(tickers):
                company_name = self._name(ticker, names)
                if needle not in ticker.casefold() and needle not in company_name.casefold():
                    continue
                results.append(
                    {
                        "ticker": ticker,
                        "company_name": company_name,
                        "owned": ticker in owned,
                        "watchlists": sorted(memberships.get(ticker, [])),
                    }
                )
        results.sort(
            key=lambda item: (
                0 if item["ticker"].casefold() == needle else 1,
                item["ticker"],
            )
        )
        return {
            "meta": self._meta(state),
            "query": str(query or "").strip(),
            "results": results[:limit],
        }

    def refresh_status(self) -> dict[str, Any]:
        state = self._refresh_state_loader()
        panel = format_refresh_panel_status(refresh_state=state)
        return {
            "environment": get_environment(),
            "status": panel["status"],
            "status_label": panel["status_label"],
            "updated_at": None if panel["updated_at"] == "–" else panel["updated_at"],
            "updated_at_source": panel["updated_at_source"],
            "last_successful_date": (state or {}).get("last_successful_date"),
            "last_error_count": (state or {}).get("last_error_count"),
        }

    def model_status(self) -> dict[str, Any]:
        state = self._state()
        return {"meta": self._meta(state), "refresh": self.refresh_status()}

    def model_data(self) -> dict[str, Any]:
        state = self._state()
        dashboard = state.context.get("dashboard") or {}
        snapshots = self._snapshots_loader()
        journal = self._discovery_journal_loader()
        decision_entries = self._decision_journal_loader()
        backtest_validation = self._backtest_validation_builder()
        snapshot_dates = (
            sorted(str(value) for value in snapshots["date"].dropna().unique())
            if isinstance(snapshots, pd.DataFrame) and not snapshots.empty and "date" in snapshots
            else []
        )
        signal_dates = (
            sorted(str(value) for value in journal["signal_date"].dropna().unique())
            if isinstance(journal, pd.DataFrame) and not journal.empty and "signal_date" in journal
            else []
        )
        decision_dates = sorted(
            {
                str(item.get("signal_date"))
                for item in decision_entries
                if isinstance(item, dict) and item.get("signal_date")
            }
        )
        return {
            "meta": self._meta(state),
            "refresh": self.refresh_status(),
            "market_regime": dashboard.get("market_regime") or {},
            "strategy_profiles": _records(dashboard.get("strategy_profiles")),
            "research_ideas": dashboard.get("research_ideas") or {},
            "snapshots": {
                "rows": len(snapshots) if isinstance(snapshots, pd.DataFrame) else 0,
                "dates": len(snapshot_dates),
                "latest_date": snapshot_dates[-1] if snapshot_dates else None,
            },
            "discovery_journal": {
                "rows": len(journal) if isinstance(journal, pd.DataFrame) else 0,
                "cohorts": len(signal_dates),
                "latest_signal_date": signal_dates[-1] if signal_dates else None,
                "status": "Prospektiv validering pågår" if signal_dates else "Ingen journaldata",
            },
            "decision_journal": {
                "entries": len(decision_entries),
                "days": len(decision_dates),
                "latest_signal_date": decision_dates[-1] if decision_dates else None,
                "status": "Råd logges" if decision_dates else "Ingen journaldata",
            },
            "backtest_validation": backtest_validation,
        }

    def chat(
        self,
        question: str,
        view: str | None = None,
        ticker: str | None = None,
        company_name: str | None = None,
    ) -> dict[str, Any]:
        state = self._state()
        if not state.context:
            raise LookupError(state.message or "Analysedata er ikke tilgjengelig.")
        contextual_question = question
        symbol = normalize_ticker(ticker) if ticker else None
        if symbol and symbol not in question.upper():
            company = str(company_name or symbol).strip()
            contextual_question = (
                f"{question}\nKontekst: Spørsmålet gjelder {symbol} ({company}) "
                f"på selskapsdetaljer-siden."
            )
        elif view:
            contextual_question = f"{question}\nKontekst: Aktiv flate er {view}."
        answer = self._chat_handler(contextual_question, state.context)
        return {"meta": self._meta(state), "answer": str(answer)}
