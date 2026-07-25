import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.universe_sources import (
    load_official_us_universe,
    parse_euronext_oslo,
    parse_nasdaq_listed,
    parse_other_listed,
)


class NasdaqSymbolParserTests(unittest.TestCase):
    def test_parses_normal_common_stocks_only(self):
        text = (
            "Symbol|Security Name|Market Category|Test Issue|Financial Status|"
            "Round Lot Size|ETF|NextShares\n"
            "AAPL|Apple Inc. - Common Stock|Q|N|N|100|N|N\n"
            "TEST|Test issue|Q|Y|N|100|N|N\n"
            "ETF1|Example ETF|Q|N|N|100|Y|N\n"
            "BAD|Bad issuer|Q|N|D|100|N|N\n"
            "WXYZ|Example Warrants|S|N|N|100|N|N\n"
            "File Creation Time: 0725202601:00|||||||\n"
        )

        self.assertEqual(parse_nasdaq_listed(text), ["AAPL"])

    def test_parses_other_exchange_and_converts_class_symbol(self):
        text = (
            "ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|"
            "Test Issue|NASDAQ Symbol\n"
            "BRK.B|Berkshire Hathaway Inc. Class B|N|BRK.B|N|100|N|BRK.B\n"
            "SPY|SPDR ETF|P|SPY|Y|100|N|SPY\n"
        )

        self.assertEqual(parse_other_listed(text), ["BRK-B"])

    def test_loads_local_snapshot(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "us_official.json"
            path.write_text(
                json.dumps({"symbols": ["AAPL", "MSFT"]}),
                encoding="utf-8",
            )
            with patch(
                "src.universe_sources.official_us_snapshot_path",
                return_value=path,
            ):
                result = load_official_us_universe()

        self.assertEqual(result, ["AAPL", "MSFT"])

    def test_parses_only_regulated_oslo_market(self):
        text = (
            '\ufeff"European Equities"\n'
            '"25 Jul 2026"\n'
            "Name;ISIN;Symbol;Market;Currency\n"
            "Company;NO1;EQNR;Oslo Børs;NOK\n"
            "Growth;NO2;GROW;Euronext Growth Oslo;NOK\n"
            "Expand;NO3;EXP;Euronext Expand Oslo;NOK\n"
            "Class;NO4;ABC.B;Oslo Børs;NOK\n"
        )

        self.assertEqual(
            parse_euronext_oslo(text),
            ["ABC-B.OL", "EQNR.OL"],
        )
