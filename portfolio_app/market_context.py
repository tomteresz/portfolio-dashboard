"""Public market context, independent of holdings and portfolio valuations."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
import json
import logging
import math
import re
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

CBOE_URL = "https://www.cboe.com/markets/us/options/market-statistics/daily"
BREADTH_URL = "https://finviz.com/"
EXCHANGE_ZONE = ZoneInfo("America/New_York")


class _Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text = []
        self.scripts = []
        self._script = None

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            self._script = []

    def handle_data(self, data):
        if self._script is not None:
            self._script.append(data)
        elif data.strip():
            self.text.append(data.strip())

    def handle_endtag(self, tag):
        if tag == "script" and self._script is not None:
            self.scripts.append("".join(self._script))
            self._script = None


def _read(url):
    request = Request(url, headers={"User-Agent": "Mozilla/5.0 MojePortfolio/0.1",
                                    "Accept": "text/html,application/json"})
    with urlopen(request, timeout=10) as response:
        body = response.read(3_000_001)
    if len(body) > 3_000_000:
        raise ValueError("Market response too large")
    return body.decode("utf-8")


def _valid_day(day, now):
    today = now.astimezone(EXCHANGE_ZONE).date()
    if not today - timedelta(days=7) <= day <= today:
        raise ValueError("Stale or future market observation")
    return day


def parse_put_call(html, now=None, *, expected_day=None):
    now = now or datetime.now(timezone.utc)
    page = _Page()
    page.feed(html)
    index = page.text.index("EQUITY PUT/CALL RATIO")
    value = float(page.text[index + 1])
    if not math.isfinite(value) or value < 0:
        raise ValueError("Invalid equity put/call ratio")
    # Cboe embeds the selected trading date in Next.js server-rendered data.
    decoded = html.replace('\\"', '"')
    match = re.search(r'"selectedDate"\s*:\s*"(\d{4}-\d{2}-\d{2})"', decoded)
    if not match:
        raise ValueError("Missing Cboe observation date")
    day = datetime.strptime(match[1], "%Y-%m-%d").date()
    if expected_day is None:
        _valid_day(day, now)
    elif day != expected_day:
        raise ValueError("Cboe returned a different trading date")
    return {"value": value, "as_of": day, "fetched_at": now}


def fetch_put_call_history():
    now = datetime.now(timezone.utc)
    today = now.astimezone(EXCHANGE_ZONE).date()
    days = [today - timedelta(days=offset) for offset in range(13, -1, -1)]

    def fetch_day(day):
        try:
            reading = parse_put_call(_read(f"{CBOE_URL}?dt={day.isoformat()}"), now, expected_day=day)
        except (OSError, ValueError, IndexError):
            return None
        return {"day": day.isoformat(), "level": reading["value"]}

    with ThreadPoolExecutor(max_workers=5) as pool:
        return [row for row in pool.map(fetch_day, (day for day in days if day.weekday() < 5))
                if row is not None]


def parse_breadth(html, now=None):
    now = now or datetime.now(timezone.utc)
    page = _Page()
    page.feed(html)
    for script in page.scripts:
        try:
            data = json.loads(script)
        except (ValueError, TypeError):
            continue
        if not isinstance(data, dict):
            continue
        for bar in data.get("marketStatsBars", []):
            if bar.get("leftTitle") != "Advancing" or bar.get("rightTitle") != "Declining":
                continue
            # Never label a narrower or unknown sample as the whole market.
            coverage = bar.get("tooltipSuffix", "")
            if not all(exchange in coverage for exchange in ("NYSE", "Nasdaq", "AMEX")):
                raise ValueError("Unknown breadth coverage")
            up, down = bar["leftCount"], bar["rightCount"]
            if any(type(v) is not int or not 0 <= v <= 100_000 for v in (up, down)) or up + down == 0:
                raise ValueError("Invalid market breadth counts")
            # Finviz exposes counts without an observation timestamp. Report
            # retrieval time explicitly rather than inventing an exchange time.
            return {"advancing": up, "declining": down, "fetched_at": now}
    raise ValueError("Market breadth unavailable")


def fetch_us10y():
    import yfinance as yf
    now = datetime.now(timezone.utc)
    closes = yf.Ticker("^TNX").history(period="5d", interval="1d",
                                       auto_adjust=False, timeout=10)["Close"].dropna().sort_index()
    if closes.empty:
        raise ValueError("US 10Y unavailable")
    value = float(closes.iloc[-1])
    if not math.isfinite(value) or value < 0:
        raise ValueError("Invalid US 10Y yield")
    day = _valid_day(closes.index[-1].date(), now)
    previous = float(closes.iloc[-2]) if len(closes) > 1 else None
    if previous is not None and (not math.isfinite(previous) or previous < 0):
        previous = None
    # Yahoo ^TNX levels are already expressed in percent, e.g. 4.25 = 4.25%.
    return {"value": value, "previous": previous, "as_of": day, "fetched_at": now}


def fetch_market_context():
    def safe(name, fetch):
        try:
            return fetch()
        except Exception as exc:
            logging.getLogger("portfolio.error").warning("%s fetch failed: %s", name, type(exc).__name__)
            return None
    jobs = {"us10y": fetch_us10y,
            "breadth": lambda: parse_breadth(_read(BREADTH_URL)),
            "put_call": lambda: parse_put_call(_read(CBOE_URL))}
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {name: pool.submit(safe, name, fetch) for name, fetch in jobs.items()}
        return {name: future.result() for name, future in futures.items()}
