from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from src.config import load_backtest_validation_config
from src.benchmarks import GLOBAL_EQUITY_BENCHMARK
from src.model_version import MODEL_VERSION
from src.signal_backtest import _get_price_data
from src.technical_baseline import (
    _affordable_shares,
    _execution,
    _prepare_prices,
)
from src.technicals import get_benchmark_for_symbol


DISCOVERY_HORIZONS = (5, 10, 20, 40)
GLOBAL_BENCHMARK = GLOBAL_EQUITY_BENCHMARK
JOURNAL_COLUMNS = [
    "signal_date",
    "model_version",
    "rank",
    "ticker",
    "region",
    "score",
    "recommendation",
    "trend_regime",
    "technical_score",
    "fundamental_score",
    "fundamental_history_score",
    "relative_strength_20d",
    "signal_price",
    "primary_profile",
    "in_watchlist",
    "global_benchmark",
    "local_benchmark",
]


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def discovery_journal_dir() -> Path:
    return _project_root() / "snapshots" / "discovery_journal"


def discovery_journal_path(signal_date: date | None = None) -> Path:
    signal_date = signal_date or date.today()
    return discovery_journal_dir() / f"discovery_{signal_date.isoformat()}.csv"


def build_discovery_journal(
    context,
    signal_date: date | None = None,
    limit: int = 3,
) -> pd.DataFrame:
    signal_date = signal_date or date.today()
    candidates = context.get("discovery_candidates")
    advisor_items = (context.get("opportunity_advisor") or {}).get("items") or []
    if not isinstance(candidates, pd.DataFrame) or candidates.empty:
        return pd.DataFrame(columns=JOURNAL_COLUMNS)

    tickers = [
        str(item.get("ticker") or "").strip().upper()
        for item in advisor_items
        if str(item.get("ticker") or "").strip()
    ][:limit]
    if not tickers:
        tickers = [
            str(ticker).strip().upper()
            for ticker in candidates["ticker"].head(limit)
        ]

    indexed = candidates.copy()
    indexed["ticker"] = indexed["ticker"].astype(str).str.strip().str.upper()
    indexed = indexed.drop_duplicates("ticker").set_index("ticker")

    rows = []
    for rank, ticker in enumerate(tickers, start=1):
        if ticker not in indexed.index:
            continue
        candidate = indexed.loc[ticker]
        rows.append({
            "signal_date": signal_date.isoformat(),
            "model_version": context.get("model_version") or MODEL_VERSION,
            "rank": rank,
            "ticker": ticker,
            "region": candidate.get("source_universe"),
            "score": candidate.get("score"),
            "recommendation": candidate.get("recommendation"),
            "trend_regime": candidate.get("trend_regime"),
            "technical_score": candidate.get("technical_score"),
            "fundamental_score": candidate.get("fundamental_score"),
            "fundamental_history_score": candidate.get(
                "fundamental_history_score"
            ),
            "relative_strength_20d": candidate.get("relative_strength_20d"),
            "signal_price": candidate.get("price"),
            "primary_profile": candidate.get("primary_profile"),
            "in_watchlist": bool(candidate.get("in_watchlist", False)),
            "global_benchmark": GLOBAL_BENCHMARK,
            "local_benchmark": get_benchmark_for_symbol(ticker),
        })

    return pd.DataFrame(rows, columns=JOURNAL_COLUMNS)


def save_discovery_journal(
    context,
    signal_date: date | None = None,
    path: Path | None = None,
) -> Path | None:
    signal_date = signal_date or date.today()
    journal = build_discovery_journal(context, signal_date=signal_date)
    if journal.empty:
        return None

    path = path or discovery_journal_path(signal_date)
    path.parent.mkdir(parents=True, exist_ok=True)
    journal.to_csv(path, index=False)
    return path


def load_discovery_journal(path: Path | None = None) -> pd.DataFrame:
    directory = path or discovery_journal_dir()
    if not directory.exists():
        return pd.DataFrame(columns=JOURNAL_COLUMNS)

    files = [directory] if directory.is_file() else sorted(directory.glob("discovery_*.csv"))
    frames = []
    for file in files:
        try:
            frame = pd.read_csv(file)
        except (OSError, pd.errors.ParserError, pd.errors.EmptyDataError):
            continue
        if set(("signal_date", "ticker")).issubset(frame.columns):
            frames.append(frame)
    if not frames:
        return pd.DataFrame(columns=JOURNAL_COLUMNS)
    return (
        pd.concat(frames, ignore_index=True)
        .drop_duplicates(["signal_date", "model_version", "ticker"], keep="last")
        .sort_values(["signal_date", "rank", "ticker"])
        .reset_index(drop=True)
    )


def _net_return(
    symbol,
    prices,
    signal_date,
    horizon_days,
    capital,
    costs,
    cost_symbol=None,
):
    return _net_returns(
        symbol,
        prices,
        signal_date,
        (horizon_days,),
        capital,
        costs,
        cost_symbol=cost_symbol,
    ).get(int(horizon_days))


def _net_returns(
    symbol,
    prices,
    signal_date,
    horizons,
    capital,
    costs,
    cost_symbol=None,
):
    prepared = _prepare_prices(
        prices,
        use_adjusted_prices=True,
    )
    future = prepared[prepared.index > pd.Timestamp(signal_date)]
    if future.empty:
        return {}

    entry = future.iloc[0]
    execution_symbol = cost_symbol or symbol
    shares = _affordable_shares(
        execution_symbol,
        capital,
        float(entry["open"]),
        costs,
    )
    if shares <= 0:
        return {}

    buy = _execution(
        execution_symbol,
        "BUY",
        float(entry["open"]),
        shares,
        costs,
    )
    cash = capital + buy["cash_change"]
    results = {}
    for horizon_days in horizons:
        horizon_days = int(horizon_days)
        if len(future) < horizon_days:
            continue
        exit_row = future.iloc[horizon_days - 1]
        sell = _execution(
            execution_symbol,
            "SELL",
            float(exit_row["close"]),
            shares,
            costs,
        )
        final_value = cash + sell["cash_change"]
        results[horizon_days] = {
            "entry_date": future.index[0].date().isoformat(),
            "exit_date": future.index[horizon_days - 1].date().isoformat(),
            "return_pct": (final_value / capital - 1) * 100,
        }
    return results


def evaluate_discovery_journal(
    journal=None,
    price_loader=None,
    config=None,
    horizons=DISCOVERY_HORIZONS,
) -> pd.DataFrame:
    journal = load_discovery_journal() if journal is None else journal
    if journal is None or journal.empty:
        return pd.DataFrame()

    config = config or load_backtest_validation_config()
    costs = config["costs"]
    initial_cash = float(config["execution"]["initial_cash"])
    loader = price_loader or (lambda symbol: _get_price_data(symbol, "1y"))
    cache = {}

    def prices_for(symbol):
        if symbol not in cache:
            cache[symbol] = loader(symbol)
        return cache[symbol]

    rows = []
    for signal_date, cohort in journal.groupby("signal_date", sort=True):
        allocation = initial_cash / len(cohort)
        for _, candidate in cohort.iterrows():
            ticker = str(candidate["ticker"])
            global_benchmark = str(
                candidate.get("global_benchmark") or GLOBAL_BENCHMARK
            )
            local_benchmark = str(
                candidate.get("local_benchmark")
                or get_benchmark_for_symbol(ticker)
            )
            for horizon in horizons:
                result = {
                    "signal_date": signal_date,
                    "model_version": candidate.get("model_version"),
                    "rank": candidate.get("rank"),
                    "ticker": ticker,
                    "region": candidate.get("region"),
                    "horizon_days": int(horizon),
                    "status": "pending",
                }
                try:
                    strategy = _net_return(
                        ticker,
                        prices_for(ticker),
                        signal_date,
                        horizon,
                        allocation,
                        costs,
                    )
                    global_result = _net_return(
                        global_benchmark,
                        prices_for(global_benchmark),
                        signal_date,
                        horizon,
                        allocation,
                        costs,
                    )
                    local_result = _net_return(
                        local_benchmark,
                        prices_for(local_benchmark),
                        signal_date,
                        horizon,
                        allocation,
                        costs,
                        cost_symbol=ticker,
                    )
                except Exception as exc:
                    result["status"] = "error"
                    result["error"] = str(exc) or exc.__class__.__name__
                else:
                    if strategy and global_result and local_result:
                        result.update({
                            "status": "complete",
                            "entry_date": strategy["entry_date"],
                            "exit_date": strategy["exit_date"],
                            "strategy_return_pct": strategy["return_pct"],
                            "global_return_pct": global_result["return_pct"],
                            "local_return_pct": local_result["return_pct"],
                            "global_difference_pct": (
                                strategy["return_pct"]
                                - global_result["return_pct"]
                            ),
                            "local_difference_pct": (
                                strategy["return_pct"]
                                - local_result["return_pct"]
                            ),
                        })
                rows.append(result)

    return pd.DataFrame(rows)


def summarize_discovery_validation(evaluation) -> dict:
    if not isinstance(evaluation, pd.DataFrame) or evaluation.empty:
        return {"journal_rows": 0, "completed": 0, "pending": 0}

    complete = evaluation[evaluation["status"] == "complete"]
    pending = evaluation[evaluation["status"] == "pending"]
    summary = {
        "journal_rows": len(evaluation),
        "completed": len(complete),
        "pending": len(pending),
        "errors": int((evaluation["status"] == "error").sum()),
    }
    if complete.empty:
        return summary

    cohorts = (
        complete.groupby(["signal_date", "horizon_days"], as_index=False)
        .agg(
            strategy_return_pct=("strategy_return_pct", "mean"),
            global_return_pct=("global_return_pct", "mean"),
            local_return_pct=("local_return_pct", "mean"),
            global_difference_pct=("global_difference_pct", "mean"),
            local_difference_pct=("local_difference_pct", "mean"),
            positions=("ticker", "count"),
        )
    )
    summary["cohorts"] = cohorts
    summary["positive_vs_global"] = int(
        (cohorts["global_difference_pct"] > 0).sum()
    )
    summary["cohort_count"] = len(cohorts)
    summary["avg_global_difference_pct"] = float(
        cohorts["global_difference_pct"].mean()
    )
    return summary
