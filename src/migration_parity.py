from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import pandas as pd

from src.model_version import MODEL_VERSION


@dataclass(frozen=True)
class ParityCheck:
    name: str
    passed: bool
    detail: str


def _records(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, pd.DataFrame):
        cleaned = value.astype(object).where(pd.notnull(value), None)
        return cleaned.to_dict(orient="records")
    if isinstance(value, list):
        return [dict(item) for item in value if isinstance(item, dict)]
    return []


def _ticker(row: dict[str, Any]) -> str:
    return str(row.get("ticker") or row.get("symbol") or "").strip().upper()


def _number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(result):
        return None
    return round(result, 4)


def _recommendation(row: dict[str, Any]) -> str | None:
    value = row.get("anbefaling", row.get("recommendation"))
    return str(value).strip() if value is not None else None


def _check(name: str, actual: Any, expected: Any) -> ParityCheck:
    return ParityCheck(
        name=name,
        passed=actual == expected,
        detail=f"forventet={expected!r}, faktisk={actual!r}",
    )


def build_migration_parity_report(
    presentation,
    context: dict[str, Any],
    portfolio: list[dict[str, Any]],
    watchlists: dict[str, list[str]],
) -> dict[str, Any]:
    """Compare the new presentation layer with Streamlit's existing sources."""
    today = presentation.today()
    explore = presentation.explore()
    positions = presentation.positions()

    watch_rows = _records(context.get("watchlist_report"))
    portfolio_rows = _records(context.get("portfolio_report"))
    source_watch = {_ticker(row): row for row in watch_rows if _ticker(row)}
    source_portfolio = {
        _ticker(row): row for row in portfolio_rows if _ticker(row)
    }
    source_positions = {_ticker(row): row for row in portfolio if _ticker(row)}
    owned_tickers = list(source_positions)
    expected_watchlist = [
        str(ticker).strip().upper()
        for ticker in dict.fromkeys(watchlists.get("Alle") or [])
        if str(ticker).strip().upper() not in source_positions
    ]

    checks = [
        _check(
            "modellversjon",
            today["meta"]["model_version"],
            context.get("model_version") or MODEL_VERSION,
        ),
        _check(
            "eide tickere",
            [row["ticker"] for row in today["owned"]],
            owned_tickers,
        ),
        _check(
            "watchlist tickere",
            [row["ticker"] for row in today["watchlist"]],
            expected_watchlist,
        ),
        _check(
            "administrer tickere",
            [row["ticker"] for row in positions["positions"]],
            owned_tickers,
        ),
    ]

    displayed = {
        row["ticker"]: row for row in today["owned"] + today["watchlist"]
    }
    for ticker, card in displayed.items():
        source = {
            **(source_portfolio.get(ticker) or {}),
            **(source_watch.get(ticker) or {}),
        }
        checks.append(
            _check(
                f"{ticker} anbefaling",
                card.get("recommendation"),
                _recommendation(source),
            )
        )
        checks.append(
            _check(
                f"{ticker} score",
                _number(card.get("score")),
                _number(source.get("score")),
            )
        )

    position_cards = {row["ticker"]: row for row in positions["positions"]}
    for ticker, source in source_positions.items():
        today_card = displayed[ticker]
        portfolio_source = source_portfolio.get(ticker) or {}
        trailing = _number(portfolio_source.get("trailing_stop_loss"))
        ordinary = _number(portfolio_source.get("stop_loss"))
        expected_stop = trailing if trailing is not None else ordinary
        checks.extend(
            [
                _check(
                    f"{ticker} GAV I dag",
                    _number(today_card.get("average_cost")),
                    _number(source.get("buy_price", source.get("average_cost"))),
                ),
                _check(
                    f"{ticker} stop-nivå",
                    _number(today_card.get("stop_level")),
                    expected_stop,
                ),
                _check(
                    f"{ticker} gevinst",
                    _number(today_card.get("gain_pct")),
                    _number(portfolio_source.get("unrealized_gain_pct")),
                ),
                _check(
                    f"{ticker} GAV Administrer",
                    _number(position_cards[ticker].get("average_cost")),
                    _number(source.get("buy_price", source.get("average_cost"))),
                ),
            ]
        )

    expected_ranking = [
        _ticker(row)
        for row in sorted(
            (row for row in watch_rows if _ticker(row) not in source_positions),
            key=lambda row: _number(row.get("score")) or -1,
            reverse=True,
        )
    ]
    checks.append(
        _check(
            "Utforsk watchlist-rangering",
            [row["ticker"] for row in explore["watchlist_ranking"]],
            expected_ranking,
        )
    )

    representative = next(iter(source_watch), None)
    if representative:
        company = presentation.company_context(representative)
        source = source_watch[representative]
        checks.extend(
            [
                _check(
                    f"{representative} selskapsanbefaling",
                    company.get("recommendation"),
                    _recommendation(source),
                ),
                _check(
                    f"{representative} selskapsscore",
                    _number(company.get("score")),
                    _number(source.get("score")),
                ),
            ]
        )

    failed = [check for check in checks if not check.passed]
    return {
        "status": "PASS" if not failed else "FAIL",
        "passed": len(checks) - len(failed),
        "failed": len(failed),
        "checks": [asdict(check) for check in checks],
    }
