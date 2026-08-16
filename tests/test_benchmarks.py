from src.benchmarks import local_benchmark_for_symbol, local_benchmark_label


def test_local_benchmark_maps_supported_markets():
    assert local_benchmark_for_symbol("NVDA") == "SPY"
    assert local_benchmark_for_symbol("kmar.ol") == "OSEBX.OL"
    assert local_benchmark_for_symbol("ERIC-B.ST") == "^OMX"
    assert local_benchmark_for_symbol("NOVO-B.CO") == "^OMXC25"
    assert local_benchmark_for_symbol("NOKIA.HE") == "^OMXH25"


def test_local_benchmark_label_uses_market_name_with_symbol_fallback():
    assert local_benchmark_label("OSEBX.OL") == "Norge"
    assert local_benchmark_label("UNKNOWN") == "UNKNOWN"
