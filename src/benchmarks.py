GLOBAL_EQUITY_BENCHMARK = "ACWI"

LOCAL_BENCHMARK_LABELS = {
    "SPY": "USA",
    "OSEBX.OL": "Norge",
    "^OMX": "Sverige",
    "^OMXC25": "Danmark",
    "^OMXH25": "Finland",
}


def local_benchmark_for_symbol(symbol: str) -> str:
    upper = str(symbol or "").strip().upper()
    if upper.endswith(".OL"):
        return "OSEBX.OL"
    if upper.endswith(".ST"):
        return "^OMX"
    if upper.endswith(".CO"):
        return "^OMXC25"
    if upper.endswith(".HE"):
        return "^OMXH25"
    return "SPY"


def local_benchmark_label(symbol: str) -> str:
    return LOCAL_BENCHMARK_LABELS.get(symbol, symbol)
