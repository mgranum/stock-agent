import re
from collections import defaultdict

SENTIMENT_METHOD = "keyword_v1"
SENTIMENT_POSITIVE = "POSITIVE"
SENTIMENT_NEGATIVE = "NEGATIVE"
SENTIMENT_NEUTRAL = "NEUTRAL"

CONFIDENCE_LOW = "LOW"
CONFIDENCE_MEDIUM = "MEDIUM"

POSITIVE_THRESHOLD = 0.25
NEGATIVE_THRESHOLD = -0.25

DISCLAIMER = "Støttesignal basert på overskrifter. Påvirker ikke anbefaling."

SENTIMENT_DISPLAY_LABELS = {
    SENTIMENT_POSITIVE: "Positiv",
    SENTIMENT_NEGATIVE: "Negativ",
    SENTIMENT_NEUTRAL: "Nøytral",
}

RULE_PATTERNS = (
    (re.compile(r"\bremains?\s+solid\b", re.IGNORECASE), "remains solid", 0.70),
    (re.compile(r"\bprice\s+target\s+raised\b", re.IGNORECASE), "price target raised", 0.75),
    (re.compile(r"\bdata\s+breach\b", re.IGNORECASE), "data breach", -0.80),
    (re.compile(r"\bcyber[\s-]?attack\b", re.IGNORECASE), "cyberattack", -0.80),
    (re.compile(r"\bin\s+red\b", re.IGNORECASE), "in red", -0.65),
    (re.compile(r"\bbeats?\s+(?:the\s+)?estimates\b", re.IGNORECASE), "beats estimates", 0.85),
    (re.compile(r"\bbeats?\b", re.IGNORECASE), "beats", 0.75),
    (re.compile(r"\braises?\s+concerns\b", re.IGNORECASE), "raises concerns", -0.55),
    (re.compile(r"\braises?\s+guidance\b", re.IGNORECASE), "raises guidance", 0.80),
    (re.compile(r"\braises?\b", re.IGNORECASE), "raises", 0.65),
    (re.compile(r"\b(?:upgraded|upgrades|upgrade)\s+to\b", re.IGNORECASE), "upgrade", 0.70),
    (re.compile(r"\b(?:upgraded|upgrades|upgrade)\b", re.IGNORECASE), "upgrade", 0.65),
    (re.compile(r"\bgains?\b", re.IGNORECASE), "gains", 0.60),
    (re.compile(r"\bresilient\b", re.IGNORECASE), "resilient", 0.60),
    (re.compile(r"\bmisses?\s+(?:the\s+)?estimates\b", re.IGNORECASE), "misses estimates", -0.85),
    (re.compile(r"\bcuts?\s+guidance\b", re.IGNORECASE), "cuts guidance", -0.80),
    (re.compile(r"\bcuts?\b", re.IGNORECASE), "cuts", -0.65),
    (re.compile(r"\b(?:downgraded|downgrades|downgrade)\s+to\b", re.IGNORECASE), "downgrade", -0.70),
    (re.compile(r"\b(?:downgraded|downgrades|downgrade)\b", re.IGNORECASE), "downgrade", -0.65),
    (re.compile(r"\bfalls?\b", re.IGNORECASE), "falls", -0.60),
    (re.compile(r"\bdrops?\b", re.IGNORECASE), "drops", -0.60),
    (re.compile(r"\blawsuit\b", re.IGNORECASE), "lawsuit", -0.75),
    (re.compile(r"\binvestigation\b", re.IGNORECASE), "investigation", -0.70),
    (re.compile(r"\bprofit\s+warning\b", re.IGNORECASE), "profit warning", -0.75),
    (re.compile(r"\bwarning\b", re.IGNORECASE), "warning", -0.60),
    (re.compile(r"\bsec\s+probe\b", re.IGNORECASE), "sec probe", -0.70),
    (re.compile(r"\brecall\b", re.IGNORECASE), "recall", -0.55),
    (re.compile(r"\bbankruptcy\b", re.IGNORECASE), "bankruptcy", -0.90),
)

POSITIVE_KEYWORDS = (
    ("strong demand", 0.55),
    ("record revenue", 0.70),
    ("record earnings", 0.70),
    ("surge", 0.50),
    ("soars", 0.55),
    ("jumps", 0.45),
    ("rally", 0.45),
    ("outperform", 0.50),
    ("buy rating", 0.55),
    ("top pick", 0.50),
)

NEGATIVE_KEYWORDS = (
    ("weak demand", -0.55),
    ("slump", -0.50),
    ("plunge", -0.55),
    ("tumble", -0.50),
    ("sinks", -0.55),
    ("layoffs", -0.60),
    ("fraud", -0.80),
    ("probe", -0.55),
    ("sell rating", -0.55),
    ("underperform", -0.50),
)


def format_sentiment_label(sentiment):
    return SENTIMENT_DISPLAY_LABELS.get(sentiment, SENTIMENT_DISPLAY_LABELS[SENTIMENT_NEUTRAL])


def _clamp_score(score):
    return max(-1.0, min(1.0, score))


def _label_from_score(score):
    if score >= POSITIVE_THRESHOLD:
        return SENTIMENT_POSITIVE
    if score <= NEGATIVE_THRESHOLD:
        return SENTIMENT_NEGATIVE
    return SENTIMENT_NEUTRAL


def analyze_headline(headline):
    text = str(headline or "").strip()
    if not text:
        return {
            "sentiment": SENTIMENT_NEUTRAL,
            "sentiment_score": 0.0,
            "sentiment_method": SENTIMENT_METHOD,
            "sentiment_signals": [],
        }

    headline_lower = text.lower()
    signals = []
    contributions = []

    for pattern, signal, weight in RULE_PATTERNS:
        if pattern.search(text):
            signals.append(signal)
            contributions.append(weight)

    for keyword, weight in POSITIVE_KEYWORDS + NEGATIVE_KEYWORDS:
        if re.search(rf"\b{re.escape(keyword)}\b", headline_lower):
            if keyword not in signals:
                signals.append(keyword)
                contributions.append(weight)

    if not contributions:
        score = 0.0
    else:
        score = _clamp_score(sum(contributions) / len(contributions))

    return {
        "sentiment": _label_from_score(score),
        "sentiment_score": score,
        "sentiment_method": SENTIMENT_METHOD,
        "sentiment_signals": signals,
    }


def analyze_news_items(items):
    analyzed = []
    for item in items or []:
        enriched = dict(item)
        enriched.update(analyze_headline(enriched.get("headline")))
        analyzed.append(enriched)
    return analyzed


def _article_weight(item):
    publisher_score = item.get("publisher_score", 0)
    try:
        publisher_score = int(publisher_score)
    except (TypeError, ValueError):
        publisher_score = 0
    return max(1, publisher_score + 4)


def _article_key(item):
    url = str(item.get("url") or "").strip().lower().rstrip("/")
    if url:
        return ("url", url)

    headline = re.sub(r"\s+", " ", str(item.get("headline") or "").strip().lower())
    ticker = str(item.get("ticker") or "").strip().upper()
    return ("headline", ticker, headline)


def _dedupe_articles(items):
    deduped = []
    seen = set()
    for item in items or []:
        key = _article_key(item)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _collect_filtered_articles(news_summary):
    portfolio_news = list(news_summary.get("portfolio_news") or [])
    watchlist_news = list(news_summary.get("watchlist_news") or [])
    return _dedupe_articles(portfolio_news + watchlist_news)


def _compute_confidence(articles):
    article_count = len(articles)
    if article_count < 2:
        return CONFIDENCE_LOW

    labels = {item.get("sentiment") for item in articles}
    if SENTIMENT_POSITIVE in labels and SENTIMENT_NEGATIVE in labels:
        return CONFIDENCE_LOW

    if article_count >= 2 and len(labels) == 1:
        return CONFIDENCE_MEDIUM

    return CONFIDENCE_LOW


def _aggregate_ticker(ticker, articles):
    weights = [_article_weight(item) for item in articles]
    total_weight = sum(weights)
    if total_weight <= 0:
        score = 0.0
    else:
        score = sum(
            item.get("sentiment_score", 0.0) * weight
            for item, weight in zip(articles, weights)
        ) / total_weight
        score = _clamp_score(score)

    positive_count = sum(
        1 for item in articles if item.get("sentiment") == SENTIMENT_POSITIVE
    )
    negative_count = sum(
        1 for item in articles if item.get("sentiment") == SENTIMENT_NEGATIVE
    )
    neutral_count = sum(
        1 for item in articles if item.get("sentiment") == SENTIMENT_NEUTRAL
    )

    in_portfolio_values = [item.get("in_portfolio") for item in articles]
    in_portfolio = any(value is True for value in in_portfolio_values)

    return {
        "ticker": ticker,
        "sentiment": _label_from_score(score),
        "score": score,
        "article_count": len(articles),
        "positive_count": positive_count,
        "negative_count": negative_count,
        "neutral_count": neutral_count,
        "confidence": _compute_confidence(articles),
        "in_portfolio": in_portfolio,
        "headlines_analyzed": len(articles),
    }


def _group_articles_by_ticker(articles):
    grouped = defaultdict(list)
    for item in articles:
        ticker = str(item.get("ticker") or "").strip().upper()
        if ticker:
            grouped[ticker].append(item)
    return grouped


def _notable_tickers(items, sentiment_label):
    return [
        item["ticker"]
        for item in items
        if item.get("sentiment") == sentiment_label
    ]


def merge_sentiment_into_news_summary(news_summary, sentiment_summary):
    if not news_summary:
        return news_summary

    articles_by_key = {
        _article_key(item): item
        for item in (sentiment_summary or {}).get("articles") or []
    }

    merged = dict(news_summary)
    merged_items = []
    for item in news_summary.get("items") or []:
        enriched = dict(item)
        sentiment_item = articles_by_key.get(_article_key(item))
        if sentiment_item:
            for field in (
                "sentiment",
                "sentiment_score",
                "sentiment_method",
                "sentiment_signals",
            ):
                enriched[field] = sentiment_item.get(field)
        merged_items.append(enriched)

    merged["items"] = merged_items
    return merged


def build_sentiment_summary(news_summary):
    if not news_summary:
        return _empty_sentiment_summary()

    source_articles = _collect_filtered_articles(news_summary)
    if not source_articles:
        return _empty_sentiment_summary(last_updated=news_summary.get("last_updated"))

    articles = analyze_news_items(source_articles)
    grouped = _group_articles_by_ticker(articles)

    items = [
        _aggregate_ticker(ticker, ticker_articles)
        for ticker, ticker_articles in sorted(grouped.items())
    ]
    portfolio_items = [item for item in items if item.get("in_portfolio")]
    watchlist_items = [item for item in items if not item.get("in_portfolio")]

    return {
        "items": items,
        "portfolio_items": portfolio_items,
        "watchlist_items": watchlist_items,
        "articles": articles,
        "notable_positive": _notable_tickers(items, SENTIMENT_POSITIVE),
        "notable_negative": _notable_tickers(items, SENTIMENT_NEGATIVE),
        "last_updated": news_summary.get("last_updated"),
        "method": SENTIMENT_METHOD,
        "disclaimer": DISCLAIMER,
    }


def _empty_sentiment_summary(last_updated=None):
    return {
        "items": [],
        "portfolio_items": [],
        "watchlist_items": [],
        "articles": [],
        "notable_positive": [],
        "notable_negative": [],
        "last_updated": last_updated,
        "method": SENTIMENT_METHOD,
        "disclaimer": DISCLAIMER,
    }
