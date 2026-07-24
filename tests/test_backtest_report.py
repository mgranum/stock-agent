import pandas as pd

from src.backtest_report import summarize_backtest_result


def test_empty_backtest_result():
    assert summarize_backtest_result(pd.DataFrame()) == (
        "Ingen backtestresultater tilgjengelig."
    )


def test_error_only_backtest_result():
    result = pd.DataFrame(
        [
            {"ticker": "AAPL", "error": "missing data"},
            {"ticker": "MSFT", "error": "missing data"},
        ]
    )

    assert summarize_backtest_result(result) == (
        "Ingen gyldige backtestresultater. Feilede kjøringer: 2."
    )
