"""Latest available minute prices from Yahoo Finance (not a tick feed)."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from functools import lru_cache
import math
import logging
from zoneinfo import ZoneInfo


def _instant(value):
    if isinstance(value, bool):
        raise ValueError("Invalid timestamp")
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, timezone.utc)
    if value.tzinfo is None:
        raise ValueError("Timestamp needs a time zone")
    return value.astimezone(timezone.utc)


def _number(value, positive=False):
    try:
        result = float(value)
        return result if not isinstance(value, bool) and math.isfinite(result) and (not positive or result > 0) else None
    except (ValueError, TypeError, OverflowError):
        return None


def regular_session_active(metadata, now=None):
    """True/False from actual exchange timestamps; None if schedule is unknown."""
    try:
        regular = metadata["currentTradingPeriod"]["regular"]
        start, end = _instant(regular["start"]), _instant(regular["end"])
        if not start < end:
            return None
        return start <= (now or datetime.now(timezone.utc)) < end
    except (KeyError, TypeError, AttributeError, ValueError, OverflowError, OSError):
        return None


def quote_regular_active(quote, now=None):
    schedule = quote.get("regular_session")
    if schedule:
        return regular_session_active({"currentTradingPeriod": {"regular": schedule}}, now)
    return quote.get("regular_session_active")


def extended_session(quote, now=None):
    """Select pre/post relative to today's actual regular-session schedule."""
    now = now or datetime.now(timezone.utc)
    try:
        regular = quote["regular_session"]
        start, end = _instant(regular["start"]), _instant(regular["end"])
        zone = ZoneInfo(quote.get("exchange_timezone") or "America/New_York")
        if start >= end or start.astimezone(zone).date() != now.astimezone(zone).date():
            return None
        if now < start:
            return "pre_market"
        if now >= end:
            return "after_hours"
    except (KeyError, TypeError, AttributeError, ValueError, OverflowError, OSError):
        pass
    return None


def extended_value(quote, field, now=None):
    """Recheck cached values at display time, including across midnight/open."""
    now = now or datetime.now(timezone.utc)
    if extended_session(quote, now) != field:
        return None
    value = quote.get(field)
    if not value:
        return None
    try:
        zone = ZoneInfo(quote.get("exchange_timezone") or "America/New_York")
        timestamp = _instant(value["timestamp"])
        if timestamp <= now and timestamp.astimezone(zone).date() == now.astimezone(zone).date():
            return value
    except (KeyError, TypeError, AttributeError, ValueError, OverflowError, OSError):
        pass
    return None


@lru_cache(maxsize=128)
def _session_close(symbol, session_date):
    import yfinance as yf
    daily = yf.Ticker(symbol).history(period="1mo", interval="1d", auto_adjust=False,
                                      prepost=False, timeout=10)["Close"].dropna()
    closes = daily[daily.index.date == session_date]
    if closes.empty:
        raise ValueError("Regular-session close is unavailable")
    value = float(closes.iloc[-1])
    if not math.isfinite(value) or value <= 0:
        raise ValueError("Invalid regular-session close")
    return value


def _extended_windows(metadata, now):
    """Only today's exchange sessions; never roll back to an older day."""
    windows = {}
    zone = ZoneInfo(metadata.get("exchangeTimezoneName") or "America/New_York")
    today = now.astimezone(zone).date()
    periods = metadata.get("currentTradingPeriod") or {}
    selected = extended_session({"regular_session": periods.get("regular"),
                                 "exchange_timezone": metadata.get("exchangeTimezoneName")}, now)
    for name, key in (("pre_market", "pre"), ("after_hours", "post")):
        if name != selected:
            continue
        try:
            period = periods[key]
            start, end = _instant(period["start"]), _instant(period["end"])
            if start < end and start <= now and start.astimezone(zone).date() == today:
                windows[name] = (start, end, today)
        except (KeyError, TypeError, AttributeError, ValueError, OverflowError, OSError):
            continue
    return windows


def _extended_change(symbol, day, name, price):
    try:
        reference = _previous_close(symbol, day) if name == "pre_market" else _session_close(symbol, day)
        return (price / reference - 1) * 100
    except Exception:
        return None


def _direct_extended(info, windows, now):
    result = {"pre_market": None, "after_hours": None}
    for name, prefix in (("pre_market", "preMarket"), ("after_hours", "postMarket")):
        if name not in windows:
            continue
        start, end, _ = windows[name]
        try:
            price = _number(info.get(prefix + "Price"), positive=True)
            timestamp = _instant(info.get(prefix + "Time"))
            if price is not None and start <= timestamp < end and timestamp <= now:
                result[name] = {"price": price, "timestamp": timestamp,
                                "change_percent": None,
                                "source": "yahoo_quote"}
        except (TypeError, AttributeError, ValueError, OverflowError, OSError):
            continue
    return result


def _extended_quotes(symbol, ticker, metadata, now=None):
    fixed_now = now
    now = now or datetime.now(timezone.utc)
    windows = _extended_windows(metadata, now)
    result = {"pre_market": None, "after_hours": None}
    history = None
    if not windows:
        # A regular-only chart may still describe the previous session before
        # the open. Ask for extended bars before deciding there is no session.
        try:
            history = ticker.history(period="1d", interval="1m", auto_adjust=False,
                                     prepost=True, timeout=10)
            metadata.update(ticker.get_history_metadata() or {})
            now = fixed_now or datetime.now(timezone.utc)
            windows = _extended_windows(metadata, now)
        except Exception as exc:
            logging.getLogger("portfolio.error").warning("Extended schedule refresh failed for %s: %s", symbol, exc)
    if not windows:
        return result
    try:
        info = ticker.get_info() or {}
        # Cold requests can cross a minute boundary. Validate timestamps against
        # receipt time, not the time before the network request started.
        now = fixed_now or datetime.now(timezone.utc)
        windows = _extended_windows(metadata, now)
        result = _direct_extended(info, windows, now)
    except Exception as exc:
        logging.getLogger("portfolio.error").warning("Direct extended quote failed for %s: %s", symbol, exc)
    # The quote endpoint can lag behind the chart even within today's session.
    # Compare timestamps instead of treating any direct quote as authoritative.
    if windows:
        try:
            if history is None:
                history = ticker.history(period="1d", interval="1m", auto_adjust=False,
                                         prepost=True, timeout=10)
            now = fixed_now or datetime.now(timezone.utc)
            windows = _extended_windows(metadata, now)
            closes = history["Close"].dropna().sort_index()
            for name in windows:
                start, end, _ = windows[name]
                candidates = closes[(closes.index >= start) & (closes.index < end) & (closes.index <= now)]
                candidates = candidates[(candidates > 0) & candidates.map(math.isfinite)]
                if not candidates.empty and (result[name] is None or
                        _instant(candidates.index[-1].to_pydatetime()) > result[name]["timestamp"]):
                    result[name] = {"price": float(candidates.iloc[-1]),
                                    "timestamp": _instant(candidates.index[-1].to_pydatetime()),
                                    "change_percent": None, "source": "yahoo_1m"}
        except Exception as exc:
            logging.getLogger("portfolio.error").warning("Extended minute bars failed for %s: %s", symbol, exc)
    for name, value in result.items():
        if name not in windows:
            result[name] = None
        elif value:
            value["change_percent"] = _extended_change(symbol, windows[name][2], name, value["price"])
    return result


@lru_cache(maxsize=128)
def _previous_close(symbol, session_date):
    """Previous session close is stable during a trading day; cache successes only."""
    import yfinance as yf
    daily = yf.Ticker(symbol).history(period="1mo", interval="1d", auto_adjust=False,
                                      prepost=False, timeout=10)["Close"].dropna()
    previous = daily[daily.index.date < session_date]
    if previous.empty:
        raise ValueError("Previous close is unavailable")
    candidate = float(previous.iloc[-1])
    if not math.isfinite(candidate) or candidate <= 0:
        raise ValueError("Invalid previous close")
    return candidate


def fetch_quote(symbol):
    import yfinance as yf

    ticker = yf.Ticker(symbol)
    history = ticker.history(
        period="1d", interval="1m", auto_adjust=False, prepost=False,
        timeout=10,
    )
    closes = history["Close"].dropna().sort_index()
    if closes.empty:
        # Before the open, Yahoo can return no regular bars for today's 1d
        # range. Keep the last regular-session valuation available so extended
        # quotes are still fetched (including on Mondays and after holidays).
        history = ticker.history(
            period="5d", interval="1m", auto_adjust=False, prepost=False,
            timeout=10,
        )
        closes = history["Close"].dropna().sort_index()
    if closes.empty:
        raise ValueError("Brak notowań w odpowiedzi dostawcy")
    price = float(closes.iloc[-1])
    if not math.isfinite(price) or price <= 0:
        raise ValueError("Nieprawidłowa cena w odpowiedzi dostawcy")
    timestamp = closes.index[-1].to_pydatetime()
    if timestamp.tzinfo is None:
        raise ValueError("Brak strefy czasowej notowania")
    # Use a daily close before the quoted session, including after hours/weekends.
    # The final minute candle is not necessarily the official closing price.
    previous_close = None
    try:
        previous_close = _previous_close(symbol, timestamp.date())
    except Exception:
        pass  # Keep the valuation available even when the daily baseline fails.
    currency, metadata = None, {}
    try:
        metadata = dict(ticker.get_history_metadata() or {})
        currency = metadata.get("currency")
    except Exception:
        pass
    if currency != "USD":
        raise ValueError("Nie potwierdzono waluty USD dla notowania.")
    extended = {"pre_market": None, "after_hours": None}
    active = regular_session_active(metadata)
    if active is False:
        try:
            extended = _extended_quotes(symbol, ticker, metadata)
        except Exception as exc:
            logging.getLogger("portfolio.error").warning("Extended-session fetch failed for %s: %s", symbol, exc)
    return {"price": price, "previous_close": previous_close, "currency": currency, "timestamp": timestamp,
            "fetched_at": datetime.now(timezone.utc), "regular_session_active": active,
            "exchange_timezone": metadata.get("exchangeTimezoneName"),
            "regular_session": (metadata.get("currentTradingPeriod") or {}).get("regular"), **extended}


def fetch_quotes(symbols):
    """Return successful quotes and per-symbol failures independently."""
    quotes, errors = {}, {}
    symbols = tuple(dict.fromkeys(symbols))
    if not symbols:
        return quotes, errors
    with ThreadPoolExecutor(max_workers=min(5, len(symbols))) as pool:
        jobs = {symbol: pool.submit(fetch_quote, symbol) for symbol in symbols}
        for symbol, job in jobs.items():
            try:
                quotes[symbol] = job.result()
            except Exception as exc:
                logging.getLogger("portfolio.error").warning("Quote fetch failed for %s: %s", symbol, exc)
                errors[symbol] = str(exc)
    return quotes, errors


def lookup_company(symbol):
    """Verify new USD stocks/ETFs and resolve their display name on demand."""
    import yfinance as yf
    try:
        info = yf.Ticker(symbol).get_info()
    except Exception as exc:
        raise ValueError("Nie udało się zweryfikować symbolu w Yahoo Finance. Spróbuj ponownie.") from exc
    if not isinstance(info, dict) or info.get("quoteType") not in ("EQUITY", "ETF"):
        raise ValueError("Nie znaleziono akcji lub ETF dla podanego symbolu.")
    if info.get("currency") != "USD":
        raise ValueError("Aplikacja obsługuje pozycje notowane w USD.")
    if _number(info.get("regularMarketPrice"), positive=True) is None:
        raise ValueError("Brak dostępnej ceny dla podanego symbolu.")
    name = info.get("shortName") or info.get("longName") or symbol
    return str(name)[:80]


def fetch_vix():
    """Cboe volatility index in points, independent of portfolio valuations."""
    import yfinance as yf
    try:
        ticker = yf.Ticker("^VIX")
        history = ticker.history(period="1d", interval="1m", auto_adjust=False,
                                 prepost=False, timeout=10)
        closes = history["Close"].dropna().sort_index()
        if closes.empty or (price := _number(closes.iloc[-1], positive=True)) is None:
            raise ValueError("Invalid VIX quote")
        stamp = closes.index[-1].to_pydatetime()
        timestamp = _instant(stamp)
        previous = None
        try:
            previous = _previous_close("^VIX", stamp.date())
        except Exception:
            pass  # Keep the level available if its daily comparison is missing.
        return {"price": price, "previous_close": previous, "timestamp": timestamp,
                "fetched_at": datetime.now(timezone.utc)}, None
    except Exception as exc:
        logging.getLogger("portfolio.error").warning("VIX fetch failed: %s", type(exc).__name__)
        return None, "Indeks VIX jest chwilowo niedostępny."


def fetch_usd_pln():
    """Independent FX quote; never include it among portfolio holdings."""
    import yfinance as yf
    try:
        ticker = yf.Ticker("PLN=X")
        history = ticker.history(period="1d", interval="1m", auto_adjust=False, timeout=10)
        closes = history["Close"].dropna()
        if closes.empty or (price := _number(closes.iloc[-1], positive=True)) is None:
            raise ValueError("Invalid FX quote")
        timestamp = _instant(closes.index[-1].to_pydatetime())
        try:
            metadata = ticker.get_history_metadata() or {}
        except Exception:
            metadata = {}
        if metadata.get("currency") not in (None, "PLN"):
            raise ValueError("Unexpected FX quote currency")
        # FX daily bars can use a different fixing from the provider's session
        # close. Use the close supplied with this intraday quote for its delta.
        previous = (_number(metadata.get("previousClose"), positive=True)
                    or _number(metadata.get("chartPreviousClose"), positive=True))
        return {"price": price, "previous_close": previous, "timestamp": timestamp,
                "currency": "PLN", "fetched_at": datetime.now(timezone.utc)}, None
    except Exception as exc:
        logging.getLogger("portfolio.error").warning("USD/PLN fetch failed: %s", type(exc).__name__)
        return None, "Kurs USD/PLN jest chwilowo niedostępny."
