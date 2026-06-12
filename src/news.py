import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

from src.company_names import get_company_name

SOURCE_YFINANCE = "yfinance"
DEFAULT_MAX_ITEMS = 8
DEFAULT_MIN_RELEVANCE_SCORE = 1
MAX_NEWS_PER_TICKER = 2
MAX_NEWS_AGE_DAYS = 14

PUBLISHER_SCORE_HIGH = 3
PUBLISHER_SCORE_MEDIUM = 1
PUBLISHER_SCORE_LOW = -3

HIGH_QUALITY_PUBLISHER_ALIASES = (
    "reuters",
    "bloomberg",
    "wsj",
    "wall street journal",
    "the wall street journal",
    "cnbc",
    "marketwatch",
    "mt newswires",
    "associated press",
    "business wire",
    "pr newswire",
    "globe newswire",
    "yahoo finance",
)

MEDIUM_QUALITY_PUBLISHER_ALIASES = (
    "barron's",
    "barrons",
    "seeking alpha",
    "zacks",
    "benzinga",
    "investor's business daily",
    "investors business daily",
)

LOW_QUALITY_PUBLISHER_ALIASES = (
    "insider monkey",
    "simply wall st.",
    "simply wall st",
    "motley fool",
    "the motley fool",
    "trefis",
)

GENERIC_HEADLINE_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bmarket talk\b",
        r"\broundup\b",
        r"\bthese stocks\b",
        r"\bstocks to buy\b",
        r"\bstock to buy\b",
        r"\bmagnificent 7\b",
        r"\bs&p 500\b",
        r"\bstock market\b",
        r"\bsector outlook\b",
        r"\brenewable energy\b.*\bstocks\b",
        r"\bbattery stocks\b",
        r"\bwhat(?:'s| is) moving\b",
        r"\bchart of the day\b",
    )
)

HEADLINE_TICKER_PATTERN = re.compile(
    r"\((?:NASDAQ|NYSE|OB|HLSE|STO|CPH|HEL|EPA|BIT|WAR)?:?"
    r"([A-Z0-9][A-Z0-9.-]{0,9})\)|"
    r"\$([A-Z]{1,6})\b|"
    r"\b(?:NASDAQ|NYSE|OB|HLSE|STO|CPH|HEL|EPA|BIT|WAR):([A-Z0-9][A-Z0-9.-]{0,9})\b"
)


def _project_root():
    return Path(__file__).resolve().parent.parent


def _cache_dir():
    cache_dir = _project_root() / "cache"
    cache_dir.mkdir(exist_ok=True)
    return cache_dir


def _cache_file(symbol):
    return _cache_dir() / f"{symbol}_news.json"


def _utc_now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize_published_at(value):
    if value is None:
        return None

    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime().astimezone(timezone.utc).isoformat(timespec="seconds")

    if isinstance(value, datetime):
        dt = value
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat(timespec="seconds")

    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc).isoformat(timespec="seconds")

    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return (
                datetime.fromisoformat(text.replace("Z", "+00:00"))
                .astimezone(timezone.utc)
                .isoformat(timespec="seconds")
            )
        except ValueError:
            return None

    return None


def _extract_url(content):
    for key in ("canonicalUrl", "clickThroughUrl"):
        url_obj = content.get(key)
        if isinstance(url_obj, dict) and url_obj.get("url"):
            return url_obj["url"]

    for key in ("link", "url"):
        direct = content.get(key)
        if isinstance(direct, str) and direct.strip():
            return direct.strip()

    return None


def _extract_publisher(content):
    provider = content.get("provider")
    if isinstance(provider, dict) and provider.get("displayName"):
        return provider["displayName"]

    publisher = content.get("publisher")
    if isinstance(publisher, str) and publisher.strip():
        return publisher.strip()

    return None


def normalize_news_item(raw, ticker):
    if not isinstance(raw, dict):
        return None

    content = raw.get("content") if isinstance(raw.get("content"), dict) else raw
    headline = content.get("title") or content.get("headline")
    if not headline or not str(headline).strip():
        return None

    published_at = normalize_published_at(
        content.get("pubDate")
        or content.get("displayTime")
        or content.get("providerPublishTime")
    )
    url = _extract_url(content)
    publisher = _extract_publisher(content)

    return {
        "ticker": str(ticker).strip().upper(),
        "headline": str(headline).strip(),
        "publisher": publisher,
        "published_at": published_at,
        "url": url,
    }


def normalize_news_items(raw_items, ticker):
    normalized = []
    for raw in raw_items or []:
        item = normalize_news_item(raw, ticker)
        if item:
            normalized.append(item)
    return normalized


def _fetch_yfinance_news(symbol):
    print(f"Henter nyheter for {symbol}")

    stock = yf.Ticker(symbol)
    try:
        raw_items = stock.news or []
    except Exception:
        raw_items = []

    items = normalize_news_items(raw_items, symbol)
    for item in items:
        item["source"] = SOURCE_YFINANCE
        item["last_updated"] = _utc_now_iso()

    return items


def _write_news_cache(cache_file, symbol, data, today=None):
    today = (today or date.today()).isoformat()
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(
            {
                "date": today,
                "symbol": symbol,
                "source": SOURCE_YFINANCE,
                "data": data,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )


def get_news(symbol, use_cache=True, today=None):
    today = today or date.today()
    today_iso = today.isoformat()
    symbol = str(symbol).strip().upper()
    cache_file = _cache_file(symbol)

    if use_cache and cache_file.exists():
        with open(cache_file, "r", encoding="utf-8") as f:
            cached = json.load(f)

        if cached.get("date") == today_iso:
            print(f"Bruker news-cache for {symbol}")
            return list(cached.get("data") or [])

    data = _fetch_yfinance_news(symbol)
    _write_news_cache(cache_file, symbol, data, today=today)
    return data


def _ordered_universe_tickers(portfolio, watchlist):
    portfolio_tickers = []
    portfolio_set = set()

    for position in portfolio or []:
        ticker = str(position.get("ticker", "")).strip().upper()
        if not ticker or ticker in portfolio_set:
            continue
        portfolio_set.add(ticker)
        portfolio_tickers.append(ticker)

    watchlist_tickers = []
    for ticker in watchlist or []:
        normalized = str(ticker).strip().upper()
        if not normalized or normalized in portfolio_set:
            continue
        if normalized not in watchlist_tickers:
            watchlist_tickers.append(normalized)

    return portfolio_tickers + watchlist_tickers, portfolio_set


def sort_news_items(items, portfolio_tickers=None):
    return _sort_by_relevance(items)


def _sort_by_relevance(items):
    return sorted(
        items,
        key=lambda item: (
            item.get("relevance_score", 0),
            item.get("published_at") or "",
        ),
        reverse=True,
    )


def _sort_newest_first(items):
    return sorted(
        items,
        key=lambda item: item.get("published_at") or "",
        reverse=True,
    )


def _normalize_publisher_name(publisher):
    return re.sub(r"\s+", " ", str(publisher or "").strip().lower())


def _publisher_matches_alias(normalized_publisher, alias):
    return alias in normalized_publisher or normalized_publisher == alias


def compute_publisher_score(publisher):
    normalized = _normalize_publisher_name(publisher)
    if not normalized:
        return 0

    if "yahoo finance video" in normalized:
        return 0

    for alias in LOW_QUALITY_PUBLISHER_ALIASES:
        if _publisher_matches_alias(normalized, alias):
            return PUBLISHER_SCORE_LOW

    for alias in HIGH_QUALITY_PUBLISHER_ALIASES:
        if _publisher_matches_alias(normalized, alias):
            return PUBLISHER_SCORE_HIGH

    for alias in MEDIUM_QUALITY_PUBLISHER_ALIASES:
        if _publisher_matches_alias(normalized, alias):
            return PUBLISHER_SCORE_MEDIUM

    return 0


def is_low_quality_publisher(publisher):
    return compute_publisher_score(publisher) == PUBLISHER_SCORE_LOW


def compute_content_relevance_score(item, company_name=None, universe_tickers=None):
    headline = item.get("headline", "")
    ticker = item.get("ticker", "")
    score = 0

    if _headline_contains_ticker(headline, ticker):
        score += 3

    if _headline_contains_company_name(headline, company_name):
        score += 2

    if headline_about_other_ticker(headline, ticker, universe_tickers=universe_tickers):
        score -= 3

    if is_generic_market_headline(headline, ticker):
        score -= 2

    return score


def compute_relevance_score(item, company_name=None, universe_tickers=None):
    publisher_score = compute_publisher_score(item.get("publisher"))
    content_score = compute_content_relevance_score(
        item,
        company_name=company_name,
        universe_tickers=universe_tickers,
    )
    return content_score + publisher_score


def _ticker_match_variants(ticker):
    normalized = str(ticker).strip().upper()
    variants = {normalized}
    if "." in normalized:
        variants.add(normalized.split(".", 1)[0])
    return variants


def _headline_contains_ticker(headline, ticker):
    headline_upper = str(headline or "").upper()
    for variant in _ticker_match_variants(ticker):
        if re.search(rf"\({re.escape(variant)}\)", headline_upper):
            return True
        if re.search(rf"\b{re.escape(variant)}\b", headline_upper):
            return True
    return False


def _significant_company_name_tokens(company_name):
    tokens = [
        token
        for token in re.split(r"[^A-Za-z0-9]+", str(company_name or ""))
        if len(token) >= 4
    ]
    if not tokens:
        return []

    stopwords = {
        "inc",
        "corp",
        "corporation",
        "company",
        "limited",
        "ltd",
        "asa",
        "group",
        "holding",
        "holdings",
        "plc",
        "publ",
        "the",
    }
    significant = [token for token in tokens if token.lower() not in stopwords]
    return significant or tokens[:1]


def _headline_contains_company_name(headline, company_name):
    if not company_name:
        return False

    headline_lower = str(headline or "").lower()
    name_lower = str(company_name).strip().lower()
    if len(name_lower) >= 4 and name_lower in headline_lower:
        return True

    tokens = _significant_company_name_tokens(company_name)
    if not tokens:
        return False

    primary = tokens[0].lower()
    if len(primary) >= 4 and re.search(rf"\b{re.escape(primary)}\b", headline_lower):
        return True

    if len(tokens) >= 2:
        pair = f"{tokens[0]} {tokens[1]}".lower()
        if pair in headline_lower:
            return True

    return False


def _extract_tickers_from_headline(headline):
    mentioned = set()
    for match in HEADLINE_TICKER_PATTERN.finditer(str(headline or "").upper()):
        for group in match.groups():
            if group:
                mentioned.add(group.strip(" .").upper())
    return mentioned


def headline_about_other_ticker(headline, ticker, universe_tickers=None):
    headline_text = str(headline or "")
    our_variants = _ticker_match_variants(ticker)
    mentioned = _extract_tickers_from_headline(headline_text)

    other_mentioned = {
        symbol
        for symbol in mentioned
        if symbol not in our_variants
    }
    if other_mentioned:
        return True

    for other_ticker in universe_tickers or []:
        other_normalized = str(other_ticker).strip().upper()
        if not other_normalized or other_normalized == str(ticker).strip().upper():
            continue
        other_variants = _ticker_match_variants(other_normalized)
        if mentioned & other_variants and not (mentioned & our_variants):
            return True

    return False


def is_generic_market_headline(headline, ticker):
    if _headline_contains_ticker(headline, ticker):
        return False

    headline_text = str(headline or "")
    return any(pattern.search(headline_text) for pattern in GENERIC_HEADLINE_PATTERNS)


def dedupe_news_items(items):
    seen_urls = set()
    seen_headlines = set()
    deduped = []

    for item in items or []:
        url_key = str(item.get("url") or "").strip().lower().rstrip("/")
        headline_key = re.sub(
            r"\s+",
            " ",
            str(item.get("headline") or "").strip().lower(),
        )

        if url_key and url_key in seen_urls:
            continue
        if headline_key and headline_key in seen_headlines:
            continue

        if url_key:
            seen_urls.add(url_key)
        if headline_key:
            seen_headlines.add(headline_key)

        deduped.append(item)

    return deduped


def limit_news_per_ticker(items, max_per_ticker=MAX_NEWS_PER_TICKER):
    grouped = {}
    for item in items or []:
        ticker = str(item.get("ticker") or "").strip().upper()
        grouped.setdefault(ticker, []).append(item)

    limited = []
    for ticker_items in grouped.values():
        ranked = sorted(
            ticker_items,
            key=lambda item: (
                item.get("relevance_score", 0),
                item.get("published_at") or "",
            ),
            reverse=True,
        )
        limited.extend(ranked[:max_per_ticker])

    return limited


def _parse_published_at_date(published_at):
    if not published_at:
        return None

    try:
        return datetime.fromisoformat(
            str(published_at).replace("Z", "+00:00")
        ).date()
    except ValueError:
        return None


def is_recent_news(item, today=None, max_age_days=MAX_NEWS_AGE_DAYS):
    published = _parse_published_at_date(item.get("published_at"))
    if published is None:
        return False

    today = today or date.today()
    return (today - published).days <= max_age_days


def filter_recent_news(items, today=None, max_age_days=MAX_NEWS_AGE_DAYS):
    today = today or date.today()
    return [
        item
        for item in (items or [])
        if is_recent_news(item, today=today, max_age_days=max_age_days)
    ]


def filter_relevant_news(
    items,
    company_names=None,
    universe_tickers=None,
    min_score=DEFAULT_MIN_RELEVANCE_SCORE,
    limit_per_ticker=True,
):
    company_names = company_names or {}
    universe_tickers = [
        str(ticker).strip().upper()
        for ticker in (universe_tickers or [])
        if ticker
    ]

    deduped = dedupe_news_items(items)
    scored = []
    for item in deduped:
        enriched = dict(item)
        ticker = enriched.get("ticker", "")
        publisher_score = compute_publisher_score(enriched.get("publisher"))
        content_score = compute_content_relevance_score(
            enriched,
            company_name=company_names.get(ticker),
            universe_tickers=universe_tickers,
        )
        enriched["publisher_score"] = publisher_score
        enriched["relevance_score"] = content_score + publisher_score
        scored.append(enriched)

    relevant = [
        item for item in scored if item.get("relevance_score", 0) >= min_score
    ]
    if limit_per_ticker:
        relevant = limit_news_per_ticker(relevant)
    return _sort_by_relevance(relevant)


def filter_news_by_scope(items, portfolio_tickers):
    portfolio_set = {
        str(ticker).strip().upper()
        for ticker in (portfolio_tickers or [])
        if ticker
    }

    portfolio_news = [
        item for item in items if item.get("ticker") in portfolio_set
    ]
    watchlist_news = [
        item for item in items if item.get("ticker") not in portfolio_set
    ]
    return portfolio_news, watchlist_news


def build_news_summary(
    portfolio=None,
    watchlist=None,
    use_cache=True,
    today=None,
    max_items=DEFAULT_MAX_ITEMS,
):
    today = today or date.today()
    tickers, portfolio_set = _ordered_universe_tickers(portfolio, watchlist)

    items = []
    for ticker in tickers:
        ticker_news = get_news(ticker, use_cache=use_cache, today=today)
        for item in ticker_news:
            enriched = dict(item)
            enriched["in_portfolio"] = ticker in portfolio_set
            items.append(enriched)

    company_names = {ticker: get_company_name(ticker) for ticker in tickers}
    items = filter_relevant_news(
        items,
        company_names=company_names,
        universe_tickers=tickers,
        limit_per_ticker=False,
    )
    items = filter_recent_news(items, today=today)
    items = limit_news_per_ticker(items)
    items = sort_news_items(items, portfolio_set)
    portfolio_news, watchlist_news = filter_news_by_scope(items, portfolio_set)
    portfolio_news = _sort_by_relevance(portfolio_news)
    watchlist_news = _sort_by_relevance(watchlist_news)

    limited_items = items[:max_items]

    last_updated_values = [
        item.get("last_updated") for item in items if item.get("last_updated")
    ]
    last_updated = max(last_updated_values) if last_updated_values else _utc_now_iso()

    return {
        "items": limited_items,
        "portfolio_news": portfolio_news,
        "watchlist_news": watchlist_news,
        "last_updated": last_updated,
    }


def build_news_table(news_summary, max_items=DEFAULT_MAX_ITEMS):
    rows = []
    for item in (news_summary.get("items") or [])[:max_items]:
        rows.append(
            {
                "Ticker": item.get("ticker", ""),
                "Overskrift": item.get("headline", ""),
                "Kilde": item.get("publisher") or "—",
                "Tidspunkt": item.get("published_at") or "—",
                "URL": item.get("url") or "",
            }
        )

    return pd.DataFrame(rows)
