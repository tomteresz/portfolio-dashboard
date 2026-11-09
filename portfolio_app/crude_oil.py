"""WTI futures quotes from Yahoo's chart endpoint, without a local cache DB."""
from datetime import datetime, timedelta, timezone
import json
import logging
import math
from urllib.request import Request, urlopen


QUOTE_URL = "https://query1.finance.yahoo.com/v8/finance/chart/CL%3DF?interval=1m&range=1d"


def _number(value):
    if isinstance(value, bool):
        raise ValueError("Invalid WTI number")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("Non-finite WTI number")
    return number


def parse_quote(payload, now=None):
    now = now or datetime.now(timezone.utc)
    chart = payload["chart"]
    if chart.get("error"):
        raise ValueError("WTI quote unavailable")
    meta = chart["result"][0]["meta"]
    if (meta["symbol"] != "CL=F" or meta["currency"] != "USD"
            or meta["instrumentType"] != "FUTURE"):
        raise ValueError("Unexpected WTI instrument")
    price = _number(meta["regularMarketPrice"])
    timestamp = datetime.fromtimestamp(_number(meta["regularMarketTime"]), timezone.utc)
    if not now - timedelta(days=7) <= timestamp <= now + timedelta(minutes=2):
        raise ValueError("Stale or future WTI quote")
    previous = meta.get("previousClose")
    if previous is None:
        previous = meta.get("chartPreviousClose")
    try:
        previous = _number(previous)
    except (TypeError, ValueError, OverflowError):
        previous = None
    change = price - previous if previous is not None else None
    percent = change / abs(previous) * 100 if previous else None
    return {"price": price, "change": change, "change_percent": percent,
            "timestamp": timestamp, "fetched_at": now}


def fetch_crude_oil():
    try:
        request = Request(QUOTE_URL, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
        with urlopen(request, timeout=10) as response:
            body = response.read(1_000_001)
        if len(body) > 1_000_000:
            raise ValueError("WTI response too large")
        return parse_quote(json.loads(body)), None
    except Exception as exc:
        logging.getLogger("portfolio.error").warning("WTI fetch failed: %s: %s", type(exc).__name__, exc)
        return None, "Kurs ropy WTI jest chwilowo niedostępny."
