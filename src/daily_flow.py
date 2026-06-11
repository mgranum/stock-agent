import pandas as pd

from src.orders import analyze_pending_orders
from src.strategy_classification import add_strategy_types


NEAR_TRAILING_STOP_PCT = 3.0
LARGE_DRAWDOWN_PCT = -15.0
CONCENTRATION_TOP_POSITION_PCT = 25.0
CONCENTRATION_TOP3_PCT = 60.0

_OPPORTUNITY_COLUMNS = [
    "ticker",
    "strategy_type",
    "score",
    "relative_strength_20d",
    "fundamental_score",
    "fundamental_history_score",
    "anbefaling",
    "trend_regime",
]


def build_daily_flow(
    watchlist_report,
    portfolio_report,
    dashboard,
    pending_orders=None,
):
    market_regime = _build_market_regime(watchlist_report, dashboard)
    key_opportunities = _build_key_opportunities(
        watchlist_report,
        dashboard,
    )
    risk_alerts = _build_risk_alerts(portfolio_report, dashboard)
    pending_summary = _build_pending_order_summary(
        pending_orders,
        watchlist_report,
        dashboard,
    )
    summary_bullets = _build_summary_bullets(
        market_regime,
        key_opportunities,
        risk_alerts,
        pending_summary,
        dashboard,
    )

    return {
        "market_regime": market_regime,
        "key_opportunities": key_opportunities,
        "risk_alerts": risk_alerts,
        "pending_orders": pending_summary,
        "summary_bullets": summary_bullets,
    }


def _build_market_regime(watchlist_report, dashboard):
    market_summary = dashboard.get("market_summary") or {}
    strategy_counts = dashboard.get("strategy_type_counts") or {}

    total = market_summary.get("total_symbols", 0)
    buy_count = market_summary.get("buy_count", 0)
    avoid_count = market_summary.get("avoid_count", 0)
    weak_avoid_count = strategy_counts.get("WEAK/AVOID", 0)

    avg_rs = 0.0
    avg_score = 0.0
    if watchlist_report is not None and not watchlist_report.empty:
        avg_rs = float(watchlist_report["relative_strength_20d"].mean())
        avg_score = float(watchlist_report["score"].mean())

    buy_ratio = buy_count / total if total else 0
    weak_ratio = weak_avoid_count / total if total else 0
    avoid_ratio = avoid_count / total if total else 0

    risk_on_points = 0
    defensive_points = 0

    if buy_ratio >= 0.25:
        risk_on_points += 1
    elif buy_ratio <= 0.10:
        defensive_points += 1

    if weak_ratio <= 0.15:
        risk_on_points += 1
    elif weak_ratio >= 0.30:
        defensive_points += 1

    if avg_rs >= 2:
        risk_on_points += 1
    elif avg_rs <= -2:
        defensive_points += 1

    if avg_score >= 60:
        risk_on_points += 1
    elif avg_score <= 45:
        defensive_points += 1

    if risk_on_points >= 3:
        label = "Risk-on"
    elif defensive_points >= 3:
        label = "Defensive"
    else:
        label = "Mixed"

    return {
        "label": label,
        "signals": {
            "buy_count": buy_count,
            "avoid_count": avoid_count,
            "weak_avoid_count": weak_avoid_count,
            "avg_relative_strength": round(avg_rs, 2),
            "avg_score": round(avg_score, 1),
            "buy_ratio_pct": round(buy_ratio * 100, 1),
            "weak_avoid_ratio_pct": round(weak_ratio * 100, 1),
            "avoid_ratio_pct": round(avoid_ratio * 100, 1),
        },
    }


def _build_key_opportunities(watchlist_report, dashboard):
    empty = {
        "new_buy_candidates": pd.DataFrame(),
        "strongest_momentum": pd.DataFrame(),
        "strongest_quality_compounders": pd.DataFrame(),
    }

    if watchlist_report is None or watchlist_report.empty:
        return empty

    classified = add_strategy_types(watchlist_report)

    new_buys = _new_buy_candidates(classified, dashboard)
    momentum = _top_by_strategy(
        classified,
        "MOMENTUM",
        sort_by=["relative_strength_20d", "score"],
    )
    quality = _top_by_strategy(
        classified,
        "QUALITY_COMPOUNDER",
        sort_by=[
            "fundamental_history_score",
            "fundamental_score",
            "score",
        ],
    )

    return {
        "new_buy_candidates": _select_opportunity_columns(new_buys, limit=5),
        "strongest_momentum": _select_opportunity_columns(momentum, limit=5),
        "strongest_quality_compounders": _select_opportunity_columns(
            quality,
            limit=5,
        ),
    }


def _new_buy_candidates(classified, dashboard):
    top_buys = dashboard.get("top_buy_candidates")
    if top_buys is not None and not top_buys.empty:
        return top_buys.copy()

    buys = classified[classified["anbefaling"] == "KJØP / ØK"].copy()
    if buys.empty:
        return pd.DataFrame()

    snapshot_changes = dashboard.get("changes_since_last_snapshot")
    if snapshot_changes is not None:
        changed = snapshot_changes.get("recommendation_changed")
        if changed is not None and not changed.empty:
            new_tickers = changed[
                changed["current_recommendation"] == "KJØP / ØK"
            ]["ticker"]
            newly_upgraded = buys[buys["ticker"].isin(new_tickers)]
            if not newly_upgraded.empty:
                return newly_upgraded.sort_values(
                    by=["score", "relative_strength_20d"],
                    ascending=[False, False],
                )

    return buys.sort_values(
        by=["score", "relative_strength_20d"],
        ascending=[False, False],
    )


def _top_by_strategy(classified, strategy_type, sort_by):
    subset = classified[
        classified["strategy_type"] == strategy_type
    ].copy()

    if subset.empty:
        return pd.DataFrame()

    return subset.sort_values(
        by=sort_by,
        ascending=[False] * len(sort_by),
    )


def _select_opportunity_columns(df, limit=5):
    if df is None or df.empty:
        return pd.DataFrame()

    if "strategy_type" not in df.columns:
        df = add_strategy_types(df)

    cols = [c for c in _OPPORTUNITY_COLUMNS if c in df.columns]
    return df[cols].head(limit).reset_index(drop=True)


def _build_risk_alerts(portfolio_report, dashboard):
    near_stop = _positions_near_trailing_stop(portfolio_report)
    weakening = dashboard.get("weakening_positions", pd.DataFrame())
    drawdowns = _large_drawdown_positions(portfolio_report)
    concentration = _concentration_risk(dashboard)
    other = dashboard.get("risk_alerts", pd.DataFrame())

    return {
        "near_trailing_stop": near_stop,
        "weakening_positions": _format_weakening_positions(weakening),
        "large_drawdowns": drawdowns,
        "concentration_risk": concentration,
        "other_alerts": other,
        "has_alerts": _has_any_alerts(
            near_stop,
            weakening,
            drawdowns,
            concentration,
            other,
        ),
    }


def _positions_near_trailing_stop(portfolio_report):
    if portfolio_report is None or portfolio_report.empty:
        return pd.DataFrame()

    df = portfolio_report.copy()
    if "error" in df.columns:
        df = df[df["error"].isna()]

    rows = []
    for _, row in df.iterrows():
        price = row.get("current_price")
        trailing = row.get("trailing_stop_loss")

        if price is None or trailing is None or pd.isna(price) or pd.isna(trailing):
            continue

        if price <= trailing:
            continue

        distance_pct = (price - trailing) / price * 100
        if distance_pct <= NEAR_TRAILING_STOP_PCT:
            rows.append({
                "ticker": row["ticker"],
                "alert": "Nær trailing stop",
                "severity": "HIGH",
                "details": (
                    f"Kurs {round(price, 2)} – "
                    f"stop {round(trailing, 2)} "
                    f"({round(distance_pct, 1)}% unna)"
                ),
            })

    return pd.DataFrame(rows)


def _large_drawdown_positions(portfolio_report):
    if portfolio_report is None or portfolio_report.empty:
        return pd.DataFrame()

    df = portfolio_report.copy()
    if "error" in df.columns:
        df = df[df["error"].isna()]

    if "unrealized_gain_pct" not in df.columns:
        return pd.DataFrame()

    losers = df[df["unrealized_gain_pct"] <= LARGE_DRAWDOWN_PCT].copy()
    if losers.empty:
        return pd.DataFrame()

    rows = []
    for _, row in losers.iterrows():
        rows.append({
            "ticker": row["ticker"],
            "alert": "Stort urealisert tap",
            "severity": "HIGH",
            "details": f"{row['unrealized_gain_pct']}%",
        })

    return pd.DataFrame(rows)


def _format_weakening_positions(weakening):
    if weakening is None or weakening.empty:
        return pd.DataFrame()

    rows = []
    for _, row in weakening.iterrows():
        details_parts = []
        if "trend_regime" in row and pd.notna(row["trend_regime"]):
            details_parts.append(str(row["trend_regime"]))
        if "relative_strength_20d" in row and pd.notna(row["relative_strength_20d"]):
            details_parts.append(f"RS {row['relative_strength_20d']}%")

        rows.append({
            "ticker": row["ticker"],
            "alert": "Svekkende posisjon",
            "severity": "MEDIUM",
            "details": " · ".join(details_parts),
        })

    return pd.DataFrame(rows)


def _concentration_risk(dashboard):
    pr = dashboard.get("portfolio_risk") or {}
    top_pct = pr.get("top_position_pct", 0)
    top3_pct = pr.get("top3_concentration_pct", 0)

    alerts = []
    if top_pct >= CONCENTRATION_TOP_POSITION_PCT:
        alerts.append({
            "alert": "Høy enkeltposisjon",
            "severity": "MEDIUM",
            "details": f"Topp posisjon {top_pct}%",
        })

    if top3_pct >= CONCENTRATION_TOP3_PCT:
        alerts.append({
            "alert": "Høy konsentrasjon (topp 3)",
            "severity": "MEDIUM",
            "details": f"Topp 3 utgjør {top3_pct}%",
        })

    return {
        "top_position_pct": top_pct,
        "top3_concentration_pct": top3_pct,
        "alerts": alerts,
        "has_risk": len(alerts) > 0,
    }


def _has_any_alerts(near_stop, weakening, drawdowns, concentration, other):
    if not near_stop.empty or not drawdowns.empty:
        return True

    if weakening is not None and not weakening.empty:
        return True

    if other is not None and not other.empty:
        return True

    return concentration.get("has_risk", False)


def _build_pending_order_summary(pending_orders, watchlist_report, dashboard):
    orders_df = dashboard.get("pending_orders")

    if orders_df is None or orders_df.empty:
        if pending_orders:
            orders_df = analyze_pending_orders(
                pending_orders,
                watchlist_report,
            )
        else:
            orders_df = pd.DataFrame()

    if orders_df is None or orders_df.empty:
        return {
            "total": 0,
            "buy_count": 0,
            "sell_count": 0,
            "orders": pd.DataFrame(),
            "summary": "Ingen ventende ordre.",
        }

    buy_count = int((orders_df["action"] == "BUY").sum())
    sell_count = int((orders_df["action"] == "SELL").sum())
    total = len(orders_df)

    parts = [f"{total} ventende ordre"]
    if buy_count:
        parts.append(f"{buy_count} kjøp")
    if sell_count:
        parts.append(f"{sell_count} salg")

    return {
        "total": total,
        "buy_count": buy_count,
        "sell_count": sell_count,
        "orders": orders_df,
        "summary": " · ".join(parts),
    }


def _build_summary_bullets(
    market_regime,
    key_opportunities,
    risk_alerts,
    pending_summary,
    dashboard,
):
    bullets = []
    signals = market_regime["signals"]

    bullets.append(
        f"Marked: {market_regime['label']} – "
        f"{signals['buy_count']} kjøp, "
        f"{signals['weak_avoid_count']} svake/unngå, "
        f"snitt RS {signals['avg_relative_strength']}%."
    )

    new_buys = key_opportunities["new_buy_candidates"]
    if not new_buys.empty:
        tickers = ", ".join(new_buys["ticker"].head(3).tolist())
        bullets.append(f"Topp kjøpskandidater: {tickers}.")

    momentum = key_opportunities["strongest_momentum"]
    if not momentum.empty:
        leader = momentum.iloc[0]["ticker"]
        rs = momentum.iloc[0]["relative_strength_20d"]
        bullets.append(f"Sterkest momentum: {leader} (RS {rs}%).")

    if risk_alerts.get("has_alerts"):
        alert_count = _count_risk_items(risk_alerts)
        bullets.append(f"{alert_count} risikovarsler krever oppmerksomhet.")
    else:
        bullets.append("Ingen kritiske risikovarsler i porteføljen.")

    if pending_summary["total"] > 0:
        bullets.append(pending_summary["summary"] + ".")

    research_summary = dashboard.get("research_ideas") or {}
    bullets.extend(_research_idea_bullets(research_summary))

    portfolio_summary = dashboard.get("portfolio_summary") or {}
    gain_pct = portfolio_summary.get("total_unrealized_gain_pct")
    if gain_pct is not None and portfolio_summary.get("positions", 0) > 0:
        bullets.append(
            f"Portefølje: {portfolio_summary['positions']} posisjoner, "
            f"urealisert {gain_pct}%."
        )

    return bullets[:8]


def _research_idea_bullets(research_summary):
    if not research_summary or research_summary.get("total", 0) == 0:
        return []

    bullets = []

    watchlist_count = research_summary.get("watchlist_count", 0)
    if watchlist_count > 0:
        tickers = ", ".join(
            idea.get("ticker", "")
            for idea in research_summary.get("watchlist_ideas", [])[:3]
            if idea.get("ticker")
        )
        if tickers:
            bullets.append(
                f"{watchlist_count} research-idé(er) bør legges til watchlist: "
                f"{tickers}."
            )
        else:
            bullets.append(
                f"{watchlist_count} research-idé(er) bør legges til watchlist."
            )

    stale_count = research_summary.get("stale_count", 0)
    if stale_count > 0:
        bullets.append(
            f"{stale_count} research-idé(er) er utdaterte (>7 dager). "
            "Oppdater i Screening."
        )

    archive_count = research_summary.get("archive_count", 0)
    if archive_count > 0:
        bullets.append(
            f"{archive_count} research-idé(er) bør arkiveres/fjernes."
        )

    return bullets


def _count_risk_items(risk_alerts):
    count = 0

    for key in ("near_trailing_stop", "weakening_positions", "large_drawdowns"):
        df = risk_alerts.get(key)
        if df is not None and not df.empty:
            count += len(df)

    other = risk_alerts.get("other_alerts")
    if other is not None and not other.empty:
        count += len(other)

    concentration = risk_alerts.get("concentration_risk") or {}
    count += len(concentration.get("alerts", []))

    return count
