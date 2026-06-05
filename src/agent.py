from src.analysis import generate_text_report
from src.ranking import ranking_table


def format_buy_recommendation(recommendation):
    if recommendation == "UNNGÅ / SELG":
        return "IKKE NY KJØPSKANDIDAT NÅ"

    if recommendation == "KJØP / ØK":
        return "AKTUELL KJØPSKANDIDAT"

    if recommendation == "HOLD / OBSERVER":
        return "OBSERVER / VENT PÅ BEDRE INNGANG"

    return recommendation


def _format_reasons(reasons):
    if isinstance(reasons, list):
        return "\n".join(f"- {reason}" for reason in reasons)

    if reasons is None:
        return "- Ingen begrunnelse tilgjengelig"

    return str(reasons)


def _format_ranking_table(df, limit=10):
    table = ranking_table(df).head(limit)

    if table.empty:
        return "Ingen aksjer å vise."

    lines = []

    for i, (_, row) in enumerate(table.iterrows(), start=1):
        lines.append(
            f"{i}. {row['ticker']} | "
            f"score {row['score']} | "
            f"{row['anbefaling']} | "
            f"{row['trend_regime']} | "
            f"RS {row['relative_strength_20d']}% | "
            f"fund {row['fundamental_score']} | "
            f"hist {row['fundamental_history_score']}"
        )

    return "\n".join(lines)


def _rank_watchlist_report(watchlist_report):
    return watchlist_report.sort_values(
        by=[
            "score",
            "fundamental_history_score",
            "fundamental_score",
            "relative_strength_20d",
        ],
        ascending=[False, False, False, False],
    )


def _screen_buy_candidates(watchlist_report):
    return _rank_watchlist_report(
        watchlist_report[
            watchlist_report["anbefaling"] == "KJØP / ØK"
        ]
    )


def _screen_quality_companies(watchlist_report):
    return _rank_watchlist_report(
        watchlist_report[
            (watchlist_report["fundamental_score"] >= 70)
            & (watchlist_report["fundamental_history_score"] >= 70)
            & (watchlist_report["score"] >= 55)
        ]
    )


def _screen_growth_with_trend(watchlist_report):
    return _rank_watchlist_report(
        watchlist_report[
            (watchlist_report["score"] >= 60)
            & (watchlist_report["fundamental_history_score"] >= 70)
            & (watchlist_report["relative_strength_20d"] > 0)
            & (watchlist_report["trend_regime"] == "STERK OPPTREND")
        ]
    )


def _screen_strong_fundamentals_not_buy(watchlist_report):
    return _rank_watchlist_report(
        watchlist_report[
            (watchlist_report["fundamental_score"] >= 70)
            & (watchlist_report["fundamental_history_score"] >= 70)
            & (watchlist_report["anbefaling"] != "KJØP / ØK")
        ]
    )


def ask_agent(question, context):
    question = question.lower()

    watchlist = context["watchlist"]
    watchlist_report = context["watchlist_report"]
    portfolio_report = context["portfolio_report"]

    is_portfolio_question = any(
        phrase in question
        for phrase in [
            "bør jeg holde",
            "bør jeg selge",
            "bør jeg redusere",
            "bør jeg øke",
            "gevinstsikre",
            "beholde",
            "min posisjon",
            "i porteføljen",
        ]
    )

    is_ranking_question = any(
        phrase in question
        for phrase in [
            "rank",
            "ranking",
            "ranger",
            "rangering",
            "sorter",
            "liste",
            "oversikt",
        ]
    )

    if (
        "kjøpskandidater" in question
        or "kjøpskandidatene" in question
        or "vis kjøp" in question
    ):
        screened = _screen_buy_candidates(watchlist_report)

        return (
            "Kjøpskandidater:\n\n"
            + _format_ranking_table(screened)
        )

    if (
        "kvalitetsselskaper" in question
        or "kvalitetsaksjer" in question
        or "sterke fundamentale" in question
        or "sterk fundamental" in question
    ):
        screened = _screen_quality_companies(watchlist_report)

        return (
            "Kvalitetsselskaper:\n\n"
            + _format_ranking_table(screened)
        )

    if (
        "vekst med trend" in question
        or "vekstaksjer med trend" in question
        or "sterk trend" in question
    ):
        screened = _screen_growth_with_trend(watchlist_report)

        return (
            "Vekst/trend-kandidater:\n\n"
            + _format_ranking_table(screened)
        )

    if (
        "sterke fundamentals men ikke kjøp" in question
        or "sterk fundamental men ikke kjøp" in question
        or "kvalitet men ikke kjøp" in question
    ):
        screened = _screen_strong_fundamentals_not_buy(watchlist_report)

        return (
            "Sterke fundamentals, men ikke kjøpskandidater nå:\n\n"
            + _format_ranking_table(screened)
        )

    if is_ranking_question:
        ranked = _rank_watchlist_report(watchlist_report)

        return (
            "Rangering av watchlist:\n\n"
            + _format_ranking_table(ranked)
        )

    if (
        "beste" in question
        or "dagens råd" in question
    ):
        filtered = watchlist_report[
            (watchlist_report["score"] >= 55)
            & (watchlist_report["relative_strength_20d"] > 0)
            & (watchlist_report["anbefaling"] != "UNNGÅ / SELG")
        ]

        top = filtered.sort_values(
            "score",
            ascending=False
        ).head(5)

        return generate_text_report(
            top,
            portfolio_report
        )

    for symbol in watchlist:
        if symbol.lower() in question:

            if (
                is_portfolio_question
                and portfolio_report is not None
            ):
                portfolio_match = portfolio_report[
                    portfolio_report["ticker"] == symbol
                ]

                if not portfolio_match.empty:
                    stock = portfolio_match.iloc[0]

                    return f"""
{symbol}

Porteføljeråd:
{stock['portefølje_råd']}

Begrunnelse:
{stock['begrunnelse']}

Gevinst/tap:
{stock['gain_pct']} %

Trend:
{stock['trend_regime']}

Total score:
{stock['score']}

Relativ styrke:
{stock['relative_strength_20d']} %

Trailing stop trigget:
{stock['trailing_stop_triggered']}

Kursmål:
{stock['kursmål']}

Stop-loss:
{stock['stop_loss']}

Trailing stop-loss:
{stock['trailing_stop_loss']}
"""

            stock = watchlist_report[
                watchlist_report["ticker"] == symbol
            ].iloc[0]

            buy_recommendation = format_buy_recommendation(
                stock["anbefaling"]
            )

            fundamental_text = _format_reasons(
                stock.get("fundamental_reasons")
            )

            fundamental_history_text = _format_reasons(
                stock.get("fundamental_history_reasons")
            )

            return f"""
{symbol}

Kjøpsvurdering:
{buy_recommendation}

Trend:
{stock['trend_regime']}

Total score:
{stock['score']}

Teknisk score:
- Trendpoeng: {stock['trend_points']}
- Momentumpoeng: {stock['momentum_points']}
- Volumpoeng: {stock['volume_points']}
- Relativ styrke: {stock['relative_strength_20d']} %

Fundamentalt snapshot:
- Fundamental score: {stock['fundamental_score']}
- Fundamental vurdering: {stock['fundamental_label']}

Fundamental begrunnelse:
{fundamental_text}

Fundamental historikk:
- Historikk-score: {stock.get('fundamental_history_score', 'N/A')}
- Historikk-vurdering: {stock.get('fundamental_history_label', 'N/A')}

Historisk begrunnelse:
{fundamental_history_text}

Kursmål:
{stock['kursmål']}

Stop-loss:
{stock['stop_loss']}

Trailing stop-loss:
{stock['trailing_stop_loss']}
"""

    return (
        "Jeg forstod ikke spørsmålet.\n\n"
        "Prøv for eksempel:\n"
        "- Ranger watchlist\n"
        "- Vis kjøpskandidater\n"
        "- Vis kvalitetsselskaper\n"
        "- Vis vekst med trend\n"
        "- Kvalitet men ikke kjøp\n"
        "- Er NVDA en kjøpskandidat?\n"
        "- Bør jeg holde NVDA?"
    )