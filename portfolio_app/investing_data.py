"""The requested Investing.com Cash instruments and their related CME futures."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import logging
import math
import re
from urllib.request import Request, urlopen

BENCHMARKS = (("US Tech 100", "1175151", "8874"), ("US 500", "1175153", "8839"))
PAGES = {"1175151": "https://www.investing.com/indices/nq-100-futures",
         "1175153": "https://www.investing.com/indices/us-spx-500-futures"}


def _quote(price, change, stamp, precision, symbol, delayed, now):
    if isinstance(price, bool) or isinstance(stamp, bool):
        raise ValueError("Invalid quote")
    price = float(price)
    timestamp = datetime.fromtimestamp(float(stamp) / 1000, timezone.utc)
    if not math.isfinite(price) or price <= 0:
        raise ValueError("Invalid quote price")
    if not now - timedelta(days=7) <= timestamp <= now + timedelta(minutes=10):
        raise ValueError("Stale or future quote")
    change = float(change) if change is not None else None
    if change is not None and not math.isfinite(change):
        change = None
    precision = int(precision)
    if not 0 <= precision <= 6:
        raise ValueError("Invalid quote precision")
    return {"price": price, "change_percent": change, "timestamp": timestamp,
            "precision": precision, "symbol": str(symbol),
            "delayed": bool(delayed), "fetched_at": now}


def parse_page(html, cash_id, future_id, now=None):
    now = now or datetime.now(timezone.utc)
    match = re.search(r'<script\b[^>]*\bid=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script\s*>', html, re.S | re.I)
    if not match:
        raise ValueError("Investing page data unavailable")
    state = json.loads(match.group(1))["props"]["pageProps"]["state"]
    if isinstance(state, str):
        state = json.loads(state)
    instrument = state["indexStore"]["instrument"]
    base = instrument["base"]
    if str(base["id"]) != cash_id or str(base["parentId"]) != future_id:
        raise ValueError("Investing returned a different instrument")
    price = instrument["price"]
    quotes = {cash_id: _quote(price["last"], price.get("changePcr"), price["lastUpdateTime"],
                             price.get("lastDecimalPrecision", 2), instrument["name"]["symbol"],
                             price.get("isDelayed", False), now)}
    errors = {}
    try:
        future = next(item for item in instrument["relatives"]["relatives"] if str(item["id"]) == future_id)
        quotes[future_id] = _quote(future["last"], future.get("changeOneDayPercent"), future["lastUpdateTime"],
                                   future.get("lastDecimalPrecision", 2), future["symbol"],
                                   str(future.get("delayed")) == "1", now)
    except (KeyError, TypeError, ValueError, OverflowError, OSError, StopIteration):
        errors[future_id] = "Futures quote unavailable"
    return quotes, errors


def _fetch_page(cash_id, future_id):
    request = Request(PAGES[cash_id] + "?cid=" + cash_id,
                      headers={"User-Agent": "MojePortfolio/1.0", "Accept": "text/html"})
    with urlopen(request, timeout=10) as response:
        body = response.read(3_000_001)
    if len(body) > 3_000_000:
        raise ValueError("Investing page too large")
    return parse_page(body.decode("utf-8"), cash_id, future_id)


def fetch_benchmarks(regular_session):
    quotes, errors = {}, {}
    # Each Cash page includes its related CME future: two HTTP requests total.
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = {(cash, future): pool.submit(_fetch_page, cash, future) for _, cash, future in BENCHMARKS}
        for (cash, future), job in jobs.items():
            try:
                values, failures = job.result()
                for quote in values.values():
                    quote["regular_session"] = regular_session
                quotes.update(values)
                errors.update(failures)
            except Exception as exc:
                logging.getLogger("portfolio.error").warning("Investing fetch failed for %s: %s", cash, type(exc).__name__)
                errors.update({cash: "Cash quote unavailable", future: "Futures quote unavailable"})
    return quotes, errors
