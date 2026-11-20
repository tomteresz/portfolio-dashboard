"""Recent company headlines from Yahoo Finance, without article bodies."""
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
import logging
from urllib.parse import urlsplit, urlunsplit
from functools import lru_cache
from threading import Lock
from langdetect import DetectorFactory, detect_langs, LangDetectException

DetectorFactory.seed = 0
_LANGUAGE_LOCK = Lock()


@lru_cache(maxsize=1024)
def is_english(text):
    try:
        # langdetect initializes shared language profiles lazily. Keep that
        # initialization safe when several company feeds arrive concurrently.
        with _LANGUAGE_LOCK:
            languages = detect_langs(text)
        return bool(languages and languages[0].lang == "en" and languages[0].prob >= .80)
    except LangDetectException:
        return False


def _image_url(value):
    if not isinstance(value, str) or any(char.isspace() or ord(char) < 32 for char in value):
        return None
    try:
        parsed = urlsplit(value)
        if parsed.scheme == "https" and parsed.hostname and parsed.username is None:
            return value
    except ValueError:
        pass
    return None


def _thumbnail_url(thumbnail):
    if not isinstance(thumbnail, dict):
        return _image_url(thumbnail)
    resolutions = thumbnail.get("resolutions")
    candidates = []
    for item in resolutions if isinstance(resolutions, list) else ():
        if isinstance(item, dict) and (url := _image_url(item.get("url"))):
            width = item.get("width")
            if type(width) is int and width > 0:
                candidates.append((width, url))
    previews = [item for item in candidates if item[0] <= 480]
    if previews:
        return max(previews)[1]
    if candidates:
        return min(candidates)[1]
    return _image_url(thumbnail.get("originalUrl"))


def normalize_news(items, symbol, now=None):
    now = now or datetime.now(timezone.utc)
    articles, seen = [], set()
    if not isinstance(items, (list, tuple)):
        return articles
    for item in items[:30]:
        if not isinstance(item, dict):
            continue
        content = item.get("content") or item
        if not isinstance(content, dict) or content.get("contentType", "STORY") not in ("STORY", "OUTLINK"):
            continue
        title = content.get("title")
        raw_url = content.get("canonicalUrl") or content.get("clickThroughUrl") or item.get("link")
        url = raw_url.get("url") if isinstance(raw_url, dict) else raw_url
        if not isinstance(title, str) or not title.strip() or not isinstance(url, str):
            continue
        declared_language = content.get("language") or content.get("lang")
        if declared_language and not str(declared_language).lower().startswith("en"):
            continue
        try:
            parsed = urlsplit(url)
            if parsed.scheme not in ("https", "http") or not parsed.hostname or parsed.username:
                continue
            url = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parsed.query, ""))
            published = content.get("pubDate") or content.get("displayTime") or item.get("providerPublishTime")
            if isinstance(published, (int, float)):
                published = datetime.fromtimestamp(published, timezone.utc)
            else:
                published = datetime.fromisoformat(str(published).replace("Z", "+00:00"))
            if published.tzinfo is None:
                continue
            published = published.astimezone(timezone.utc)
        except (ValueError, TypeError, OverflowError, OSError):
            continue
        if not now - timedelta(days=7) <= published <= now + timedelta(minutes=10):
            continue
        # Where Yahoo supplies related symbols, exclude unrelated feed items.
        finance = content.get("finance")
        related = finance.get("stockTickers") if isinstance(finance, dict) else []
        related = related if isinstance(related, list) else []
        related_symbols = {value for r in related
                           if isinstance(value := r.get("symbol") if isinstance(r, dict) else r, str)}
        if related_symbols and symbol not in related_symbols:
            continue
        title_key = title.strip().casefold()
        if url in seen or title_key in seen:
            continue
        # Validate and deduplicate cheaply before running language detection.
        text = " ".join(str(value)[:2000] for value in
                        (title, content.get("summary") or "", content.get("description") or "") if value)
        if not is_english(title[:500]) or not is_english(text):
            continue
        seen.update((url, title_key))
        provider = content.get("provider") or {}
        publisher = provider.get("displayName") if isinstance(provider, dict) else str(provider)
        thumbnail = _thumbnail_url(content.get("thumbnail"))
        if thumbnail is None and content is not item:
            thumbnail = _thumbnail_url(item.get("thumbnail"))
        articles.append({"title": title.strip(), "url": url, "published": published,
                         "source": publisher or item.get("publisher") or "Yahoo Finance", "symbols": [symbol],
                         "thumbnail": thumbnail})
    return sorted(articles, key=lambda a: a["published"], reverse=True)


def fetch_company_news(symbol):
    import yfinance as yf
    try:
        yf.config.locale.lang = "en-US"
        yf.config.locale.region = "US"
        items = yf.Ticker(symbol).get_news(count=30, tab="news")
        return normalize_news(items or [], symbol), None, datetime.now(timezone.utc)
    except Exception as exc:
        logging.getLogger("portfolio.error").warning("News fetch failed for %s: %s", symbol, exc)
        return [], "Nie udało się pobrać wiadomości.", datetime.now(timezone.utc)


def fetch_news_batch(symbols):
    """Fetch each company once, with bounded concurrent network requests."""
    symbols = tuple(dict.fromkeys(symbols))
    if not symbols:
        return {}
    with ThreadPoolExecutor(max_workers=min(4, len(symbols))) as pool:
        return dict(zip(symbols, pool.map(fetch_company_news, symbols)))


def select_headlines(feeds, per_company=10, limit=10):
    combined = []
    by_url, by_title = {}, {}
    for articles in feeds:
        for article in articles[:per_company]:
            title = article["title"].casefold()
            duplicate = by_url.get(article["url"]) or by_title.get(title)
            if duplicate:
                duplicate["symbols"] = sorted(set(duplicate["symbols"] + article["symbols"]))
                if not duplicate.get("thumbnail") and article.get("thumbnail"):
                    duplicate["thumbnail"] = article["thumbnail"]
            else:
                duplicate = {**article, "symbols": list(article["symbols"])}
                combined.append(duplicate)
            by_url[article["url"]] = duplicate
            by_title[title] = duplicate
    return sorted(combined, key=lambda a: a["published"], reverse=True)[:limit]
