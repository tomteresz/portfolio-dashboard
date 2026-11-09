"""Sector ETF performance and upcoming US economic releases."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from html import unescape
import json
import logging
import math
import re
from zoneinfo import ZoneInfo

from portfolio_app.market_context import _read, _Page

NY = ZoneInfo("America/New_York")
BLS_URL = "https://www.bls.gov/schedule/news_release/bls.ics"
FED_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
BEA_URL = "https://www.bea.gov/news/schedule"
FF_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
SECTORS = {
    "XLK": "Technologia", "XLF": "Finanse", "XLE": "Energia",
    "XLV": "Ochrona zdrowia", "XLI": "Przemysł", "XLB": "Materiały",
    "XLY": "Dobra uznaniowe", "XLP": "Dobra podstawowe", "XLU": "Użyteczność publiczna",
    "XLRE": "Nieruchomości", "XLC": "Usługi komunikacyjne",
}


def fetch_sectors():
    import yfinance as yf
    result = {symbol: None for symbol in SECTORS}
    try:
        history = yf.download(list(SECTORS), period="5d", interval="1d", auto_adjust=False,
                              threads=4, progress=False, timeout=10)["Close"].sort_index()
        today = datetime.now(NY).date()
        for symbol in SECTORS:
            if symbol not in history:
                continue
            closes = history[symbol].dropna()
            if len(closes) < 2:
                continue
            current, previous = float(closes.iloc[-1]), float(closes.iloc[-2])
            day = closes.index[-1].date()
            if (all(math.isfinite(x) and x > 0 for x in (current, previous))
                    and today - timedelta(days=7) <= day <= today):
                result[symbol] = {"change": (current / previous - 1) * 100, "day": day}
    except Exception as exc:
        logging.getLogger("portfolio.error").warning("Sector map fetch failed: %s", type(exc).__name__)
    return result


def _event(title, source, day, when=None):
    return {"title": title, "source": source, "day": day, "when": when}


def parse_bls(text):
    events = []
    text = re.sub(r"\r?\n[ \t]", "", text)
    if "BEGIN:VCALENDAR" not in text:
        raise ValueError("Invalid BLS calendar")
    for block in text.split("BEGIN:VEVENT")[1:]:
        title = re.search(r"^SUMMARY:(.*)$", block, re.M)
        start = re.search(r"^DTSTART([^:]*):([^\r\n]+)", block, re.M)
        if not title or not start:
            continue
        title = title[1].strip().replace(r"\,", ",").replace(r"\n", " ")
        if not any(word in title for word in ("Consumer Price Index", "Employment Situation", "Producer Price Index", "Employment Cost")):
            continue
        raw = start[2].strip()
        if len(raw) == 8:
            day = datetime.strptime(raw, "%Y%m%d").date()
            events.append(_event(title, "BLS", day))
        else:
            zone = re.search(r'TZID="?([^;"\r\n]+)', start[1])
            zone_name = zone[1] if zone else "America/New_York"
            if zone_name in ("US-Eastern", "Eastern Standard Time"):
                zone_name = "America/New_York"
            tz = timezone.utc if raw.endswith("Z") else ZoneInfo(zone_name)
            when = datetime.strptime(raw.rstrip("Z"), "%Y%m%dT%H%M%S").replace(tzinfo=tz)
            events.append(_event(title, "BLS", when.astimezone(NY).date(), when))
    return events


def parse_fed(html):
    events = []
    for section in re.split(r"(?=\d{4} FOMC Meetings)", html)[1:]:
        year = int(section[:4])
        matches = re.findall(r'fomc-meeting__month[^>]*>\s*<strong>([^<]+)</strong>.*?fomc-meeting__date[^>]*>([^<]+)', section, re.S)
        for month, days in matches:
            month = month.strip().split("/")[-1]
            end = re.findall(r"\d+", days)
            if not end:
                continue
            month_number = datetime.strptime(month[:3], "%b").month
            day = datetime(year, month_number, int(end[-1])).date()
            # The meeting calendar confirms the date, not an exact release time.
            events.append(_event("FOMC · decyzja w sprawie stóp", "Federal Reserve", day))
    if not events:
        raise ValueError("FOMC dates unavailable")
    return events


def _plain(html):
    page = _Page()
    page.feed(html)
    return unescape(" ".join(page.text))


def parse_bea(html):
    # The schedule groups its table rows by a year heading.
    year_match = re.search(r'(?:Year\s*|<h[234][^>]*>\s*)(20\d{2})', html)
    if not year_match:
        raise ValueError("BEA schedule year unavailable")
    year = int(year_match[1])
    events = []
    for row in re.findall(r"<tr\b[^>]*>(.*?)</tr>", html, re.S | re.I):
        heading = re.search(r'(20\d{2})', _plain(row)) if '<th' in row else None
        if heading:
            year = int(heading[1])
        title = re.search(r'<td[^>]*class="release-title[^>]*>(.*?)</td>', row, re.S)
        day = re.search(r'class="release-date"[^>]*>([^<]+)', row)
        clock = re.search(r'(\d{1,2}:\d{2}\s*[AP]M)', _plain(row))
        if not title or not day or not clock:
            continue
        title = _plain(title[1])
        if not (title.startswith("GDP (") or title.startswith("Personal Income and Outlays")):
            continue
        when = datetime.strptime(f"{year} {day[1].strip()} {clock[1]}", "%Y %B %d %I:%M %p").replace(tzinfo=NY)
        events.append(_event(title, "BEA", when.date(), when))
    if not events:
        raise ValueError("BEA releases unavailable")
    return events


def parse_forex_factory(text):
    payload = json.loads(text)
    if not isinstance(payload, list):
        raise ValueError("Invalid economic calendar")
    events = []
    for item in payload:
        title = item.get("title", "")
        if item.get("country") != "USD" or not any(word in title for word in ("CPI", "Non-Farm Employment", "Unemployment Rate", "Average Hourly Earnings", "PPI")):
            continue
        when = datetime.fromisoformat(item["date"])
        if when.tzinfo is None:
            continue
        events.append(_event(title, "Forex Factory", when.astimezone(NY).date(), when))
    return events


def fetch_macro_calendar():
    sources = {"BLS": (BLS_URL, parse_bls), "Federal Reserve": (FED_URL, parse_fed),
               "BEA": (BEA_URL, parse_bea)}
    events, failures = [], []
    def fetch(url, parser):
        return parser(_read(url))
    with ThreadPoolExecutor(max_workers=3) as pool:
        jobs = {name: pool.submit(fetch, *args) for name, args in sources.items()}
        for name, job in jobs.items():
            try:
                events.extend(job.result())
            except Exception as exc:
                failures.append(name)
                logging.getLogger("portfolio.error").warning("Macro calendar %s failed: %s", name, type(exc).__name__)
    if "BLS" in failures:
        try:
            events.extend(fetch(FF_URL, parse_forex_factory))
        except Exception as exc:
            logging.getLogger("portfolio.error").warning("Macro fallback failed: %s", type(exc).__name__)
    return {"events": events, "failures": failures, "fetched_at": datetime.now(timezone.utc)}


def upcoming_macro(events, now=None):
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(NY).date()
    unique = {}
    for event in events:
        if not today <= event["day"] <= today + timedelta(days=45):
            continue
        if event["when"] is not None and event["when"] < now:
            continue
        key = (event["title"], event["day"], event["when"])
        unique[key] = event
    return sorted(unique.values(), key=lambda e: (e["day"], e["when"] or datetime.combine(e["day"], datetime.min.time(), NY)))[:30]
