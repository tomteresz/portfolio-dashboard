"""Upcoming earnings and declared dividends; never infer a payout from annual yield."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import logging
import math
from urllib.parse import quote
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import pandas as pd

EXCHANGE_TIMEZONE = ZoneInfo("America/New_York")


def exchange_today():
    return datetime.now(EXCHANGE_TIMEZONE).date()


def _date(value):
    if value is None or isinstance(value, (int, float, bool)):
        return None
    try:
        stamp = pd.to_datetime(value, errors="coerce")
        if not isinstance(stamp, pd.Timestamp) or pd.isna(stamp):
            return None
        if stamp.tzinfo is not None:
            stamp = stamp.tz_convert(EXCHANGE_TIMEZONE)
        return stamp.date()
    except (TypeError, ValueError, OverflowError):
        return None


def upcoming_earnings(values, today=None):
    today = today or exchange_today()
    if not isinstance(values, (list, tuple)):
        return []
    return sorted({day for value in values if (day := _date(value)) is not None and day >= today})


def normalize_dividends(payload, today=None):
    today = today or exchange_today()
    data = payload.get("data") or {}
    if (payload.get("status") or {}).get("rCode", 200) != 200:
        raise ValueError("Dividend source unavailable")
    rows = (data.get("dividends") or {}).get("rows") or []
    result, seen = [], set()
    for row in rows:
        if not isinstance(row, dict) or row.get("type") != "Cash":
            continue
        ex_date, payment = _date(row.get("exOrEffDate")), _date(row.get("paymentDate"))
        if not any(day is not None and day >= today for day in (ex_date, payment)):
            continue
        raw = row.get("amount")
        currency = row.get("currency") or ("USD" if isinstance(raw, str) and "$" in raw else None)
        currency = currency.strip() if isinstance(currency, str) else None
        try:
            amount = float(str(raw).replace("$", "").replace(",", "").strip())
            if not math.isfinite(amount) or amount < 0 or not currency:
                amount = None
        except (TypeError, ValueError, OverflowError):
            amount = None
        identity = (ex_date, payment, amount, currency)
        if identity in seen:
            continue
        seen.add(identity)
        result.append({"ex_date": ex_date, "payment_date": payment, "amount": amount,
                       "currency": currency, "source": "Nasdaq"})
    return sorted(result, key=lambda d: d["payment_date"] or d["ex_date"])


def _nasdaq_dividends(symbol):
    url = f"https://api.nasdaq.com/api/quote/{quote(symbol, safe='')}/dividends?assetclass=stocks"
    request = Request(url, headers={"User-Agent": "MojePortfolio/1.0", "Accept": "application/json"})
    with urlopen(request, timeout=8) as response:
        body = response.read(2_000_001)
    if len(body) > 2_000_000:
        raise ValueError("Dividend response too large")
    return normalize_dividends(json.loads(body))


def fetch_company_calendar(symbol):
    import yfinance as yf
    today = exchange_today()
    result = {"earnings": [], "dividends": [], "dividend_payer": None,
              "issues": [], "fetched_at": datetime.now(timezone.utc)}
    ticker = yf.Ticker(symbol)
    calendar = {}
    try:
        response = ticker.get_calendar()
        if response is not None and not isinstance(response, dict):
            raise ValueError("Invalid calendar response")
        calendar = response or {}
        result["earnings"] = upcoming_earnings(calendar.get("Earnings Date"), today)
        if not result["earnings"]:
            dates = ticker.get_earnings_dates(limit=8)
            if dates is not None and not dates.empty:
                upcoming = upcoming_earnings(list(dates.index), today)
                result["earnings"] = upcoming[:1]
    except Exception as exc:
        logging.getLogger("portfolio.error").warning("Earnings fetch failed for %s: %s", symbol, type(exc).__name__)
        result["issues"].append("Yahoo Finance")
    try:
        result["dividends"] = _nasdaq_dividends(symbol)
    except Exception as exc:
        logging.getLogger("portfolio.error").warning("Dividend fetch failed for %s: %s", symbol, type(exc).__name__)
        result["issues"].append("Nasdaq")
    # Yahoo may know a forthcoming date even when no amount is available.
    # Never combine a historical amount or annual dividend rate with that date.
    if not result["dividends"]:
        ex_date, payment = _date(calendar.get("Ex-Dividend Date")), _date(calendar.get("Dividend Date"))
        ex_date = ex_date if ex_date is not None and ex_date >= today else None
        payment = payment if payment is not None and payment >= today else None
        if ex_date or payment:
            result["dividends"] = [{"ex_date": ex_date, "payment_date": payment,
                                    "amount": None, "currency": None, "source": "Yahoo Finance"}]
    if result["dividends"]:
        result["dividend_payer"] = True
    else:
        try:
            # Used only to decide visibility, never as a future payout amount.
            info = ticker.get_info() or {}
            rate = info.get("dividendRate")
            if rate is None:
                rate = info.get("trailingAnnualDividendRate")
            if rate is not None and not isinstance(rate, bool):
                rate = float(rate)
                if math.isfinite(rate) and rate >= 0:
                    result["dividend_payer"] = rate > 0
        except Exception as exc:
            logging.getLogger("portfolio.error").warning("Dividend status failed for %s: %s", symbol, type(exc).__name__)
            if "Yahoo Finance" not in result["issues"]:
                result["issues"].append("Yahoo Finance")
    return result


def fetch_calendars(symbols):
    symbols = tuple(dict.fromkeys(symbols))
    if not symbols:
        return {}
    with ThreadPoolExecutor(max_workers=min(4, len(symbols))) as pool:
        return dict(zip(symbols, pool.map(fetch_company_calendar, symbols)))
