from __future__ import annotations

import csv
import io
import json
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

NASDAQ_LISTED_URL = (
    "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
)
OTHER_LISTED_URL = (
    "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"
)
EURONEXT_OSLO_URL = (
    "https://live.euronext.com/en/product_directory/data/"
    "stocks-oslo/download?mics=MERK%2CXOAS%2CXOSL"
)
NASDAQ_NORDIC_SCREENER_URL = (
    "https://api.nasdaq.com/api/nordic/screener/shares"
)
NASDAQ_NORDIC_MARKETS = {
    "CPH": ".CO",
    "STO": ".ST",
    "HEL": ".HE",
}
NASDAQ_NORDIC_SEGMENTS = ("LARGE_CAP", "MID_CAP", "SMALL_CAP")

_EXCLUDED_NAME_PARTS = (
    " warrant",
    " warrants",
    " unit",
    " units",
    " right",
    " rights",
    " preferred",
    " preference",
)


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def official_us_snapshot_path() -> Path:
    return _project_root() / "data" / "universes" / "us_official.json"


def official_norway_snapshot_path() -> Path:
    return _project_root() / "data" / "universes" / "norway_official.json"


def official_nordics_snapshot_path() -> Path:
    return _project_root() / "data" / "universes" / "nordics_official.json"


def _yahoo_symbol(symbol: str) -> str:
    return symbol.strip().upper().replace(".", "-")


def _is_common_equity(row, symbol_key, *, financial_status_key=None) -> bool:
    symbol = str(row.get(symbol_key) or "").strip()
    name = f" {str(row.get('Security Name') or '').lower()}"
    if not symbol or symbol.startswith("File Creation Time"):
        return False
    if row.get("ETF") != "N" or row.get("Test Issue") != "N":
        return False
    if financial_status_key and row.get(financial_status_key) != "N":
        return False
    if any(part in name for part in _EXCLUDED_NAME_PARTS):
        return False
    return "$" not in symbol and "^" not in symbol


def parse_nasdaq_listed(text: str) -> list[str]:
    rows = csv.DictReader(io.StringIO(text), delimiter="|")
    return [
        _yahoo_symbol(row["Symbol"])
        for row in rows
        if _is_common_equity(
            row,
            "Symbol",
            financial_status_key="Financial Status",
        )
    ]


def parse_other_listed(text: str) -> list[str]:
    rows = csv.DictReader(io.StringIO(text), delimiter="|")
    return [
        _yahoo_symbol(row["ACT Symbol"])
        for row in rows
        if _is_common_equity(row, "ACT Symbol")
    ]


def refresh_official_us_universe() -> Path:
    with urlopen(NASDAQ_LISTED_URL, timeout=30) as response:
        nasdaq_text = response.read().decode("utf-8")
    with urlopen(OTHER_LISTED_URL, timeout=30) as response:
        other_text = response.read().decode("utf-8")

    symbols = sorted(set(parse_nasdaq_listed(nasdaq_text) + parse_other_listed(other_text)))
    if not symbols:
        raise ValueError("Nasdaq Symbol Directory ga et tomt USA-univers.")

    path = official_us_snapshot_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "snapshot_version": 1,
        "snapshot_date": date.today().isoformat(),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_urls": [NASDAQ_LISTED_URL, OTHER_LISTED_URL],
        "symbols": symbols,
    }
    with open(path, "w", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, ensure_ascii=False)
    return path


def load_official_us_universe() -> list[str] | None:
    path = official_us_snapshot_path()
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as stream:
        payload = json.load(stream)
    symbols = payload.get("symbols")
    if not isinstance(symbols, list) or not symbols:
        return None
    return [str(symbol).strip().upper() for symbol in symbols if str(symbol).strip()]


def parse_euronext_oslo(text: str) -> list[str]:
    lines = text.lstrip("\ufeff").splitlines()
    try:
        header_index = next(
            index for index, line in enumerate(lines) if line.startswith("Name;")
        )
    except StopIteration:
        return []

    symbols = []
    rows = csv.DictReader(lines[header_index:], delimiter=";")
    for row in rows:
        symbol = str(row.get("Symbol") or "").strip().upper()
        if not symbol or row.get("Market") != "Oslo Børs":
            continue
        yahoo_symbol = symbol.replace(".", "-")
        if not yahoo_symbol.endswith(".OL"):
            yahoo_symbol = f"{yahoo_symbol}.OL"
        symbols.append(yahoo_symbol)
    return sorted(set(symbols))


def refresh_official_norway_universe() -> Path:
    with urlopen(EURONEXT_OSLO_URL, timeout=30) as response:
        text = response.read().decode("utf-8-sig")
    symbols = parse_euronext_oslo(text)
    if not symbols:
        raise ValueError("Euronext ga et tomt Oslo Børs-univers.")

    path = official_norway_snapshot_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    snapshot = {
        "snapshot_version": 1,
        "snapshot_date": date.today().isoformat(),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_urls": [EURONEXT_OSLO_URL],
        "market": "XOSL",
        "symbols": symbols,
    }
    with open(path, "w", encoding="utf-8") as stream:
        json.dump(snapshot, stream, indent=2, ensure_ascii=False)
    return path


def load_official_norway_universe() -> list[str] | None:
    path = official_norway_snapshot_path()
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as stream:
        payload = json.load(stream)
    symbols = payload.get("symbols")
    if not isinstance(symbols, list) or not symbols:
        return None
    return [str(symbol).strip().upper() for symbol in symbols if str(symbol).strip()]


def parse_nasdaq_nordic_rows(payload: dict, suffix: str) -> list[str]:
    rows = (
        payload.get("data", {})
        .get("instrumentListing", {})
        .get("rows", [])
    )
    symbols = []
    for row in rows:
        if row.get("assetClass") != "SHARES":
            continue
        symbol = str(row.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        yahoo_symbol = "-".join(symbol.replace(".", "-").split())
        symbols.append(f"{yahoo_symbol}{suffix}")
    return sorted(set(symbols))


def _nasdaq_nordic_url(market: str, segment: str) -> str:
    query = urlencode(
        {
            "category": "MAIN_MARKET",
            "market": market,
            "segment": segment,
            "tableonly": "true",
        }
    )
    return f"{NASDAQ_NORDIC_SCREENER_URL}?{query}"


def refresh_official_nordics_universe() -> Path:
    symbols_by_market = {}
    source_urls = []
    for market, suffix in NASDAQ_NORDIC_MARKETS.items():
        market_symbols = []
        for segment in NASDAQ_NORDIC_SEGMENTS:
            url = _nasdaq_nordic_url(market, segment)
            source_urls.append(url)
            request = Request(
                url,
                headers={
                    "Accept": "application/json, text/plain, */*",
                    "Origin": "https://www.nasdaq.com",
                    "Referer": "https://www.nasdaq.com/",
                    "User-Agent": "Mozilla/5.0",
                },
            )
            with urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
            market_symbols.extend(parse_nasdaq_nordic_rows(payload, suffix))
        symbols_by_market[market] = sorted(set(market_symbols))

    symbols = sorted(
        {
            symbol
            for market_symbols in symbols_by_market.values()
            for symbol in market_symbols
        }
    )
    if not symbols or any(not values for values in symbols_by_market.values()):
        raise ValueError("Nasdaq ga et tomt eller ufullstendig Norden-univers.")

    path = official_nordics_snapshot_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    snapshot = {
        "snapshot_version": 1,
        "snapshot_date": date.today().isoformat(),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_urls": source_urls,
        "category": "MAIN_MARKET",
        "segments": list(NASDAQ_NORDIC_SEGMENTS),
        "symbols_by_market": symbols_by_market,
        "symbols": symbols,
    }
    with open(path, "w", encoding="utf-8") as stream:
        json.dump(snapshot, stream, indent=2, ensure_ascii=False)
    return path


def load_official_nordics_universe() -> list[str] | None:
    path = official_nordics_snapshot_path()
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as stream:
        payload = json.load(stream)
    symbols = payload.get("symbols")
    if not isinstance(symbols, list) or not symbols:
        return None
    return [str(symbol).strip().upper() for symbol in symbols if str(symbol).strip()]


if __name__ == "__main__":
    print(refresh_official_us_universe())
    print(refresh_official_norway_universe())
    print(refresh_official_nordics_universe())
