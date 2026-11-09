"""US equity Fear & Greed readings from FearGreedFlow's documented free API."""
from datetime import date, datetime, timedelta, timezone
import json
import logging
import math
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

SOURCE_URL = "https://feargreedflow.com/data"
DATA_URL = "https://feargreedflow.com/api/fear-greed"


def normalize_sentiment(payload, now=None):
    now = now or datetime.now(timezone.utc)
    dates, values = payload["dates"], payload["values"]
    if not isinstance(dates, list) or not isinstance(values, list) or not dates or len(dates) != len(values):
        raise ValueError("Invalid sentiment series")
    score = float(values[-1])
    if isinstance(values[-1], bool) or not math.isfinite(score) or not 0 <= score <= 100:
        raise ValueError("Invalid sentiment score")
    timestamp = datetime.fromisoformat(str(payload["asOf"]).replace("Z", "+00:00"))
    if timestamp.tzinfo is None:
        raise ValueError("Sentiment timestamp needs a time zone")
    today = now.astimezone(ZoneInfo("America/New_York")).date()
    reading_date = date.fromisoformat(dates[-1])
    if not today - timedelta(days=7) <= reading_date <= today:
        raise ValueError("Stale or future sentiment reading")
    if not now - timedelta(days=7) <= timestamp <= now + timedelta(minutes=10):
        raise ValueError("Stale or future sentiment timestamp")
    if score < 25:
        rating = "Skrajny strach"
    elif score < 45:
        rating = "Strach"
    elif score <= 55:
        rating = "Neutralny"
    elif score < 75:
        rating = "Chciwość"
    else:
        rating = "Skrajna chciwość"
    return {"score": score, "rating": rating, "timestamp": timestamp.astimezone(timezone.utc)}


def fetch_sentiment():
    request = Request(DATA_URL, headers={"User-Agent": "MojePortfolio/1.0", "Accept": "application/json"})
    try:
        with urlopen(request, timeout=8) as response:
            body = response.read(2_000_001)
        if len(body) > 2_000_000:
            raise ValueError("Sentiment response too large")
        return normalize_sentiment(json.loads(body)), None
    except HTTPError as exc:
        logging.getLogger("portfolio.error").warning("FearGreedFlow HTTP status: %s", exc.code)
    except (URLError, TimeoutError, OSError, ValueError, KeyError, TypeError, OverflowError) as exc:
        logging.getLogger("portfolio.error").warning("FearGreedFlow unavailable: %s", type(exc).__name__)
    return None, "Fear & Greed Index jest chwilowo niedostępny."
