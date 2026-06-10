import logging
import re
from typing import List

import feedparser

logger = logging.getLogger(__name__)

GOOGLE_NEWS_RSS = (
    "https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
)
_MAX_ARTICLES = 5


def _to_coin_name(symbol: str) -> str:
    parts = symbol.split("/")
    raw = parts[0].strip()
    raw = re.sub(r"[^A-Z0-9]", "", raw)
    return raw


def check_news(symbol: str) -> List[str]:
    coin = _to_coin_name(symbol)
    if not coin:
        return []
    query = f"{coin}+cryptocurrency"
    url = GOOGLE_NEWS_RSS.format(q=query)

    try:
        feed = feedparser.parse(url)
    except Exception as e:
        logger.warning(f"{symbol}: news fetch failed — {e}")
        return []

    if feed.bozo and not feed.entries:
        logger.warning(f"{symbol}: RSS parse error — {feed.bozo_exception}")
        return []

    titles = []
    for entry in feed.entries[: _MAX_ARTICLES]:
        title = entry.get("title", "").strip()
        if title:
            titles.append(title)

    return titles
