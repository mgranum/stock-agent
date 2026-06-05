from src.ranking import rank_watchlist


def screen_stocks(
    symbols,
    min_score=55,
    min_fundamental_score=None,
    min_fundamental_history_score=None,
    min_relative_strength=None,
    trend_regime=None,
    recommendation=None,
    pause_seconds=1,
):
    df = rank_watchlist(
        symbols,
        pause_seconds=pause_seconds,
    )

    if df.empty:
        return df

    if min_score is not None:
        df = df[df["score"] >= min_score]

    if min_fundamental_score is not None:
        df = df[df["fundamental_score"] >= min_fundamental_score]

    if min_fundamental_history_score is not None:
        df = df[
            df["fundamental_history_score"]
            >= min_fundamental_history_score
        ]

    if min_relative_strength is not None:
        df = df[df["relative_strength_20d"] >= min_relative_strength]

    if trend_regime is not None:
        df = df[df["trend_regime"] == trend_regime]

    if recommendation is not None:
        df = df[df["anbefaling"] == recommendation]

    return df.reset_index(drop=True)


def screen_quality_companies(symbols, pause_seconds=1):
    return screen_stocks(
        symbols,
        min_score=55,
        min_fundamental_score=70,
        min_fundamental_history_score=70,
        pause_seconds=pause_seconds,
    )


def screen_growth_with_trend(symbols, pause_seconds=1):
    return screen_stocks(
        symbols,
        min_score=60,
        min_fundamental_history_score=70,
        min_relative_strength=0,
        trend_regime="STERK OPPTREND",
        pause_seconds=pause_seconds,
    )


def screen_buy_candidates(symbols, pause_seconds=1):
    return screen_stocks(
        symbols,
        recommendation="KJØP / ØK",
        pause_seconds=pause_seconds,
    )


def screen_strong_fundamentals_weak_technical(symbols, pause_seconds=1):
    return screen_stocks(
        symbols,
        min_fundamental_score=70,
        min_fundamental_history_score=70,
        pause_seconds=pause_seconds,
    ).query("anbefaling != 'KJØP / ØK'")