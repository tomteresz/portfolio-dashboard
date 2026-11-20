from datetime import date, datetime, timedelta, timezone
from html import escape
from hashlib import sha256
import math
import sqlite3
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from portfolio_app.market_data import (
    fetch_quotes, fetch_usd_pln, fetch_vix, fetch_daily_history, lookup_company,
    quote_regular_active, extended_value, extended_session,
)
from portfolio_app.investing_data import BENCHMARKS, fetch_benchmarks
from portfolio_app.crude_oil import fetch_crude_oil
from portfolio_app.holdings_table import column_metadata, render_table
from portfolio_app.company_news import fetch_news_batch, select_headlines
from portfolio_app.company_logos import ticker_logo
from portfolio_app.parallel_data import parallel_loads
from portfolio_app.company_calendar import exchange_today, fetch_calendars, upcoming_earnings
from portfolio_app.market_sentiment import SOURCE_URL as SENTIMENT_SOURCE_URL, fetch_sentiment
from portfolio_app.market_context import EXCHANGE_ZONE, fetch_market_context
from portfolio_app.breadth_history import BREADTH_HISTORY_DAYS, load_breadth_history
from portfolio_app.market_overview import SECTORS, fetch_sectors, fetch_macro_calendar, upcoming_macro
from portfolio_app.auth import require_login, logout_button, is_authenticated
from portfolio_app.i18n import tr, language, language_selector
from portfolio_app.app_logging import configure_logs
from portfolio_app.layout_store import COLUMNS, LABELS, columns_for, save_columns
from portfolio_app.portfolio_store import PORTFOLIOS, add_position, load_positions, remove_position, update_position, validate_position
from portfolio_app.portfolio_names import load_portfolio_names, rename_portfolio

st.set_page_config(page_title="MyPortfolio manager", page_icon="📈", layout="wide", initial_sidebar_state="collapsed")
configure_logs()
require_login()
st.markdown(tr("""
<style>
.block-container {max-width:1500px; padding-top:4.5rem; padding-bottom:2rem;}
h1,h2,h3 {letter-spacing:-.025em;}
h1 {font-size:1.9rem !important; padding-bottom:.4rem !important;}
[data-testid="stSidebar"] {border-right:1px solid #ddd;}
[data-testid="stMetric"] {padding:16px 18px; border:1px solid #e4e8ed;
    background:linear-gradient(145deg,#fff,#fafbfd); border-radius:12px;
    box-shadow:0 3px 12px #172b4405; min-height:102px;}
[data-testid="stMetricLabel"] {color:#68717b; font-size:.78rem;}
[data-testid="stMetricValue"] {font-size:1.65rem; font-weight:650; letter-spacing:-.025em;}
[data-testid="stMetric"] {text-align:center !important;}
[data-testid="stMetricLabel"] {display:flex !important; justify-content:center !important; gap:.25rem;}
[data-testid="stMetricLabel"] > div {justify-content:center !important;}
[data-testid="stMetricValue"] {display:flex !important; justify-content:center !important;}
[data-testid="stMetric"] [data-testid="stMarkdownContainer"],
[data-testid="stMetric"] [data-testid="stMarkdownContainer"] p {text-align:center !important;}
[data-testid="stMetricDelta"] {justify-content:center !important; width:fit-content; margin-inline:auto !important;}
[data-testid="stVerticalBlockBorderWrapper"] {border-radius:3px;}
[data-baseweb="tab-list"] {gap:8px; border-bottom:1px solid #d9dde3; padding-top:10px;}
[data-baseweb="tab"] {padding:12px 26px; font-weight:600; border-radius:8px 8px 0 0;}
[data-baseweb="tab-highlight"] {background:#eda325; height:3px;}
[data-baseweb="tab"][aria-selected="true"] {color:#202833; background:#fff7e8;}
.masthead {background:radial-gradient(ellipse at top right,#394553,transparent 70%),#1d252e;
    color:#fff; padding:20px 26px; margin-bottom:12px; border-radius:14px;
    display:flex; justify-content:space-between; align-items:center; border-bottom:3px solid #eda325;
    box-shadow:0 8px 24px #16263712;}
.brand {font-size:1.3rem; line-height:1.5; font-weight:750; letter-spacing:-.04em;}
.brand span {color:#eda325;}
.masthead-note {color:#d2dae3; font-size:.7rem; letter-spacing:.12em;
    border:1px solid #ffffff26; border-radius:20px; padding:7px 13px;}
.quote-strip {display:flex; flex-wrap:wrap; border:1px solid #e4e8ed; border-radius:12px;
    margin-top:1.5rem; margin-bottom:14px; background:#fff; box-shadow:0 3px 12px #172b4405; overflow:hidden;}
.quote {padding:16px 20px; border-right:1px solid #e9edf1; font-size:.82rem; flex:1; min-width:150px;}
.quote:last-child {border-right:0;}
.quote strong {color:#23659a; margin-right:10px;}
.ticker-logo {width:28px;height:28px;object-fit:contain;vertical-align:middle;
    margin-right:8px;border-radius:6px;background:#f5f7fa;font-size:0;}
.quote-price {font-weight:600; margin-right:8px; font-variant-numeric:tabular-nums;}
.up,.down,.neutral {display:inline-block; padding:3px 7px; border-radius:5px;
    font-weight:600; font-size:.76rem; font-variant-numeric:tabular-nums;}
.up {color:#168047; background:#eaf6ee;} .down {color:#c33935; background:#fceeee;}
[class*="st-key-change-up-"] [data-testid="stMetricValue"] {color:#168047;}
[class*="st-key-change-down-"] [data-testid="stMetricValue"] {color:#c33935;}
.neutral {color:#707780; background:#f1f3f5;}
.section-label {font-size:.75rem; font-weight:700; color:#68717b; text-transform:uppercase;
    letter-spacing:.07em; border-bottom:1px solid #e1e4e8; padding:10px 0; margin-bottom:8px;}
.portfolio-name {font-size:1.15rem; font-weight:650; margin:16px 0 6px;
    padding-left:12px; border-left:3px solid #eda325;}
.portfolio-sub {font-size:.8rem; color:#68717b; margin-bottom:14px;}
.daily-drivers {max-width:840px; margin:0 auto; border:1px solid #e4e8ed; border-radius:12px;
    padding:12px 16px; background:#fff;}
.daily-drivers h3 {font-size:1rem; margin:0 0 8px; padding:0;}
.daily-drivers-grid {display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,265px),1fr));
    gap:8px 24px;}
.daily-drivers table {width:100%; border-collapse:collapse; font-size:.82rem; font-variant-numeric:tabular-nums;}
.daily-drivers th,.daily-drivers td {padding:4px 0 4px 8px; text-align:right; white-space:nowrap;}
.daily-drivers th:first-child,.daily-drivers td:first-child {text-align:left; padding-left:0; white-space:normal;
    overflow-wrap:anywhere;}
.daily-drivers thead {color:#68717b; border-bottom:1px solid #e4e8ed;}
.daily-drivers caption {text-align:left; color:inherit; font-weight:650; padding-bottom:4px;}
.daily-drivers-footer {display:flex; flex-wrap:wrap; gap:4px 20px; border-top:1px solid #e4e8ed;
    margin-top:8px; padding-top:8px; font-size:.82rem; font-variant-numeric:tabular-nums;}
.daily-drivers-note {display:block; margin-top:4px; color:#68717b; font-size:.73rem;}
[data-testid="stDataFrame"] {border-radius:10px; overflow:hidden; border:1px solid #e4e8ed;}
.mobile-holdings {display:none;}
.holding-card {background:#fff; border:1px solid #e4e8ed; border-radius:12px; padding:16px; margin-bottom:12px;}
.extended-grid {display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,260px),1fr));gap:12px;margin:12px 0;}
.extended-row {display:flex;justify-content:space-between;align-items:center;gap:8px;margin-top:14px;font-size:.9rem;flex-wrap:wrap;}
.extended-time {color:#68717b;font-size:.73rem;margin-top:5px;}
.holding-title {display:flex; justify-content:space-between; align-items:center; gap:10px; font-weight:650;}
.holding-title small {display:block; color:#68717b; font-size:.75rem; font-weight:400;}
.holding-title > div {min-width:0;overflow-wrap:anywhere;}
.holding-card {min-width:0;overflow-wrap:anywhere;}
.sector-map {display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,160px),1fr));gap:10px;margin:12px 0;}
.sector-tile {border-radius:10px;padding:16px;min-height:110px;box-sizing:border-box;overflow-wrap:anywhere;border:1px solid #e4e8ed;}
.sector-tile strong,.sector-tile span {display:block;}
.sector-tile strong {font-size:.9rem;} .sector-tile span {font-size:1.4rem;margin-top:8px;font-weight:650;}
.sector-tile small {display:block;margin-top:7px;font-size:.7rem;}
.holding-details {display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px; margin-top:16px;}
.holding-details dt {font-size:.75rem; color:#68717b;}
.holding-details dd {margin:3px 0 0; font-size:.95rem; font-variant-numeric:tabular-nums; overflow-wrap:anywhere;}
@media(max-width:1100px) {
    .mobile-holdings {display:block;}
    [class*="st-key-desktop-holdings-"] {display:none;}
    .block-container {padding-left:1rem; padding-right:1rem;}
}
[data-testid="stExpander"] {background:#fff; border-radius:10px;}
[data-testid="stButton"] button {border-radius:8px; border-color:#dde3e9;
    background:#fff; box-shadow:0 2px 5px #172b4405; font-weight:600;}
[data-testid="stButton"] button:hover {border-color:#d98b12; background:#fff9ed; color:#9c6410;}
@media(prefers-reduced-motion:no-preference) {
    [data-testid="stButton"] button {transition:background .15s,border-color .15s;}}
@media(max-width:640px) {.masthead {padding:12px;} .masthead-note {display:none;}
    [data-baseweb="tab"] {padding:10px 12px; min-height:44px;}
    .quote {padding:10px 12px; min-width:125px;}
    [data-testid="stButton"] button {min-height:44px;}
    [data-testid="stMetricValue"] {font-size:1.45rem;}
    input,textarea,select {font-size:16px !important;}
    h1 {font-size:1.6rem !important;}}
</style>
"""), unsafe_allow_html=True)

COLORS = {"INTC": "#8062d6", "MSFT": "#3e98b5", "AMZN": "#e6ae58", "GOOGL": "#64b79c"}
DISPLAY_TIMEZONE = ZoneInfo("Europe/Warsaw")
BENCHMARK_CHARTS = {"1175151": ("Nasdaq 100", "^NDX"), "1175153": ("S&P 500", "^GSPC")}


def portfolio_label(portfolio):
    return st.session_state.get("portfolio-names", {}).get(portfolio, portfolio)


def display_time(value, pattern="%Y-%m-%d %H:%M"):
    return value.astimezone(DISPLAY_TIMEZONE).strftime(pattern + " %Z")


@st.cache_data(ttl=55, max_entries=8, show_spinner=False)
def load_quotes(symbols):
    return fetch_quotes(symbols)


@st.cache_data(ttl=55, max_entries=1, show_spinner=False)
def load_usd_pln():
    return fetch_usd_pln()


@st.cache_data(ttl=600, max_entries=8, show_spinner=False)
def load_news(symbols):
    return fetch_news_batch(symbols)


@st.cache_data(ttl=55, max_entries=1, show_spinner=False)
def load_vix():
    return fetch_vix()


@st.cache_data(ttl=300, max_entries=6, show_spinner=False)
def load_daily_history(symbol):
    return fetch_daily_history(symbol, positive=symbol not in ("CL=F", "^TNX"))


@st.cache_data(ttl=55, max_entries=1, show_spinner=False)
def load_crude_oil():
    return fetch_crude_oil()


@st.cache_data(ttl=600, max_entries=1, show_spinner=False)
def load_market_context():
    return fetch_market_context()


@st.cache_data(ttl=300, max_entries=1, show_spinner=False)
def load_sectors():
    return fetch_sectors()


@st.cache_data(ttl=21600, max_entries=1, show_spinner=False)
def load_macro_calendar():
    return fetch_macro_calendar()


@st.cache_data(ttl=55, max_entries=1, show_spinner=False)
def load_benchmarks(regular_session):
    return fetch_benchmarks(regular_session)


@st.cache_data(ttl=600, max_entries=1, show_spinner=False)
def load_sentiment():
    return fetch_sentiment()


def load_calendars(symbols):
    snapshot = st.session_state.setdefault("calendar-snapshot", {})
    missing = tuple(sorted(set(symbols) - set(snapshot)))
    if missing:
        # Reserve every symbol, including failures, so reruns never retry it.
        for symbol in missing:
            snapshot[symbol] = {"earnings": [], "dividends": [],
                                "issues": ["Yahoo Finance / Nasdaq"], "fetched_at": None}
        try:
            fetched = fetch_calendars(missing)
            for symbol in missing:
                if isinstance(fetched.get(symbol), dict):
                    snapshot[symbol].update(fetched[symbol])
        except Exception:
            configure_logs()[1].exception("Could not fetch the session calendar")
    return {symbol: snapshot[symbol] for symbol in symbols}


def render_calendar(part, name, all_symbols):
    with st.expander(tr("Kalendarz wyników i dywidend — wszystkie portfele"), expanded=False,
                     key=f"calendar-{name}", on_change="rerun") as calendar:
        if not calendar.open:
            return
        part = part.groupby("Ticker", as_index=False, sort=False).agg({
            "Spółka": "first",
            "Portfel": lambda values: " · ".join(portfolio_label(value) for value in dict.fromkeys(values)),
            "Akcje": "sum",
        })
        with st.spinner(tr("Pobieranie kalendarza…")):
            symbols = tuple(sorted(set(all_symbols) | set(part["Ticker"])))
            data = load_calendars(symbols)
        today = exchange_today()
        cards, issues, times = [], [], []
        for _, holding in part.iterrows():
            symbol = holding["Ticker"]
            events = data.get(symbol) or {"earnings": [], "dividends": [],
                                         "issues": ["Yahoo Finance / Nasdaq"], "fetched_at": None}
            if events["fetched_at"] is not None:
                times.append(events["fetched_at"])
            issues.extend(f'{symbol} ({source})' for source in events["issues"] or [])
            earnings = upcoming_earnings(events["earnings"], today)
            dividends = [d for d in events["dividends"] or []
                         if any(day is not None and day >= today for day in (d["ex_date"], d["payment_date"]))]
            company = f'<strong>{escape(symbol)}</strong> · {escape(holding["Spółka"])}'
            company += f'<div class="extended-time">{escape(holding["Portfel"])}</div>'
            rows = []
            event_dates = list(earnings)
            if earnings:
                date_text = earnings[0].strftime("%d.%m.%Y")
                if len(earnings) > 1:
                    date_text += " – " + earnings[-1].strftime("%d.%m.%Y")
            else:
                date_text = "—"
            rows.append(f'<div class="extended-row"><span>{tr("Wyniki finansowe")}</span><strong>{date_text}</strong></div>')
            for dividend in dividends:
                amount = dividend["amount"]
                amount_text = "—" if amount is None else f'{amount:g} {escape(dividend["currency"])}'
                ex_text = dividend["ex_date"].strftime("%d.%m.%Y") if dividend["ex_date"] else "—"
                pay_text = dividend["payment_date"].strftime("%d.%m.%Y") if dividend["payment_date"] else "—"
                event_date = min(day for day in (dividend["ex_date"], dividend["payment_date"]) if day is not None and day >= today)
                event_dates.append(event_date)
                total = None if amount is None else amount * float(holding["Akcje"])
                total_text = "—" if total is None or not math.isfinite(total) else f'{total:,.2f} {escape(dividend["currency"])}'
                rows.append(f'<div class="extended-row"><span>{tr("Dywidenda / akcję brutto")}</span><strong>{amount_text}</strong></div>'
                            f'<div class="extended-row"><span>{tr("Łącznie brutto (szacunek)")}</span><strong>{total_text}</strong></div>'
                            f'<div class="extended-row"><span>Ex-dividend</span><strong>{ex_text}</strong></div>'
                            f'<div class="extended-row"><span>{tr("Dzień wypłaty")}</span><strong>{pay_text}</strong></div>'
                            f'<div class="extended-time">{escape(dividend["source"])}</div>')
            if not dividends and events.get("dividend_payer") is True:
                rows.append(f'<div class="extended-row"><span>{tr("Dywidenda / akcję brutto")}</span><strong>—</strong></div>'
                            f'<div class="extended-row"><span>{tr("Łącznie brutto (szacunek)")}</span><strong>—</strong></div>'
                            '<div class="extended-row"><span>Ex-dividend</span><strong>—</strong></div>'
                            f'<div class="extended-row"><span>{tr("Dzień wypłaty")}</span><strong>—</strong></div>')
            cards.append((min(event_dates) if event_dates else date.max,
                          f'<article class="holding-card">{company}{"".join(rows)}</article>'))
        if cards:
            st.html('<div class="extended-grid">' + "".join(card for _, card in sorted(cards, key=lambda item: item[0])) + '</div>')
        else:
            st.info(tr("Brak zapowiedzianych wydarzeń dla spółek z tego portfela."))
        if issues:
            st.caption(tr("Niepełne dane kalendarza: ") + ", ".join(issues))
        if times:
            st.caption(tr("Ostatnie sprawdzenie: ") + display_time(min(times)))


def render_news(symbols):
    with st.expander(tr("Wiadomości spółek"), expanded=True, key="company-news", on_change="rerun") as news:
        if not news.open:
            return
        if st.button(tr("↻ Odśwież wiadomości"), key="refresh-news"):
            load_news.clear()
        feeds, failures, times = [], [], []
        with st.spinner(tr("Pobieranie wiadomości…")):
            news_by_symbol = load_news(symbols)
            for symbol in symbols:
                articles, error, fetched = news_by_symbol[symbol]
                feeds.append(articles)
                times.append(fetched)
                if error:
                    failures.append(symbol)
        if failures:
            st.warning(tr("Brak dostępu do wiadomości dla: " + ", ".join(failures) + "."))
        articles = select_headlines(feeds)
        if not articles:
            st.info(tr("Brak aktualnych wiadomości dla spółek w portfelach."))
        for article in articles:
            st.caption(tr(f'{" · ".join(article["symbols"])} · {article["source"]} · {display_time(article["published"], "%d.%m.%Y %H:%M")}'))
            st.html(tr(f'<a href="{escape(article["url"], quote=True)}" target="_blank" '
                    f'rel="noopener noreferrer" style="color:#23659a;font-weight:600;line-height:1.5;'
                    f'display:block;min-height:44px;box-sizing:border-box;padding:8px 0 14px;border-bottom:1px solid #e4e8ed;'
                    f'overflow-wrap:anywhere">{escape(article["title"])}</a>'))
        if times:
            st.caption(tr("Ostatnie sprawdzenie: ") + display_time(min(times), "%H:%M"))


def value_positions(quotes, records):
    positions = pd.DataFrame(records).rename(columns={
        "portfolio": "Portfel", "name": "Spółka", "symbol": "Ticker",
        "shares": "Akcje", "average_price": "Średnia",
    })
    positions["Cena"] = positions["Ticker"].map(lambda symbol: quotes[symbol]["price"])
    positions["Kapitał"] = positions["Akcje"] * positions["Średnia"]
    positions["Wartość"] = positions["Akcje"] * positions["Cena"]
    positions["Zwrot USD"] = positions["Wartość"] - positions["Kapitał"]
    positions["Zwrot %"] = (positions["Cena"] / positions["Średnia"] - 1) * 100
    positions["Poprzednie zamknięcie"] = positions["Ticker"].map(
        lambda symbol: quotes[symbol].get("previous_close")
    ).astype(float)
    positions["Wartość poprzednia"] = positions["Akcje"] * positions["Poprzednie zamknięcie"]
    positions["Zmiana dzienna USD"] = positions["Wartość"] - positions["Wartość poprzednia"]
    positions["Sesja"] = positions["Ticker"].map(lambda symbol: quotes[symbol]["timestamp"].date())
    positions["Zmiana dzienna %"] = (positions["Cena"] / positions["Poprzednie zamknięcie"] - 1) * 100
    now = datetime.now(timezone.utc)
    for label, field in (("Pre-market", "pre_market"), ("After-hours", "after_hours")):
        values = {symbol: extended_value(quote, field, now) or {} for symbol, quote in quotes.items()}
        positions[label] = positions["Ticker"].map({s: v.get("price") for s, v in values.items()}).astype(float)
        positions[label + " %"] = positions["Ticker"].map({s: v.get("change_percent") for s, v in values.items()}).astype(float)
    return positions


def daily_change(positions):
    if positions["Wartość poprzednia"].isna().any() or positions["Sesja"].nunique() != 1:
        return None
    return (positions["Wartość"].sum() / positions["Wartość poprzednia"].sum() - 1) * 100


def daily_metric(target, positions):
    change = daily_change(positions)
    amount = None if change is None else positions["Wartość"].sum() - positions["Wartość poprzednia"].sum()
    target.metric(tr("Zmiana dzienna"), "—" if change is None else f"{change:+.2f}%",
                  delta=None if amount is None else f"{amount:+,.2f} USD",
                  help=tr("Względem zamknięcia sesji poprzedzającej datę ostatniego notowania. "
                       "Wynik portfela ważony wartością pozycji na poprzednim zamknięciu."))


def return_metric(target, positions):
    value, cost = positions["Wartość"].sum(), positions["Kapitał"].sum()
    target.metric(tr("Zwrot od zakupu"), f"{(value / cost - 1) * 100:+.2f}%",
                  delta=f"{value - cost:+,.2f} USD",
                  help=tr("Zmiana wartości portfela względem zainwestowanego kapitału. "
                       "Bez dywidend, prowizji i wpływu kursów walut."))


def daily_driver_rates(day, quote):
    live = quote is not None and quote["timestamp"].astimezone(EXCHANGE_ZONE).date() == day
    rate = quote["price"] if live else None
    previous = quote.get("previous_close") if live else None
    if previous is None and (live or day < datetime.now(EXCHANGE_ZONE).date()):
        history = load_daily_history("PLN=X")
        session = day.isoformat()
        if not live:
            rate = next((point["level"] for point in history if point["day"] == session), None)
        previous = next((point["level"] for point in reversed(history) if point["day"] < session), None)
    return rate, previous, live


def render_daily_drivers(positions, quote):
    day = positions["Sesja"].iloc[0]
    rate, previous_rate, live = daily_driver_rates(day, quote)
    if rate is not None:
        rate = round(rate, 4)
    by_ticker = positions.groupby("Ticker")["Zmiana dzienna USD"].sum()
    tables = []
    for title, amounts, color in (
        ("Największy dodatni wkład", by_ticker[by_ticker > 0].nlargest(3), "up"),
        ("Największy ujemny wkład", by_ticker[by_ticker < 0].nsmallest(3), "down"),
    ):
        rows = []
        for symbol, usd in amounts.items():
            pln = "—" if rate is None else f'{usd * rate:+,.2f}'
            rows.append(f'<tr><th scope="row">{escape(symbol)}</th>'
                        f'<td><span class="{color}">{usd:+,.2f}</span></td><td>{pln}</td></tr>')
        body = "".join(rows) or f'<tr><td colspan="3">{escape(tr("Brak pozycji"))}</td></tr>'
        tables.append(f'<table><caption>{escape(tr(title))}</caption><thead><tr>'
                      '<th scope="col">Ticker</th><th scope="col">USD</th><th scope="col">PLN</th>'
                      f'</tr></thead><tbody>{body}</tbody></table>')

    fx_text, total_text = "—", "—"
    note = tr("Brakuje kursu USD/PLN dla tej sesji lub jego poprzedniego zamknięcia.")
    if rate is not None and previous_rate is not None:
        previous_value = positions["Wartość poprzednia"].sum()
        # Use prior USD exposure for FX so the price and FX terms add to the PLN change.
        fx_amount = previous_value * (rate - round(previous_rate, 4))
        total_amount = by_ticker.sum() * rate + fx_amount
        fx_text, total_text = f'{fx_amount:+,.2f} PLN', f'{total_amount:+,.2f} PLN'
        note = tr("Wkład spółek w PLN po bieżącym kursie. Wpływ waluty względem poprzedniego zamknięcia USD/PLN.")
        if not live:
            note = tr("Do przeliczenia użyto historycznego zamknięcia USD/PLN z dnia") + f" {day:%d.%m.%Y}."

    heading = escape(tr("Co dziś zmieniło wartość portfela?"))
    st.html(f'<section class="daily-drivers" aria-label="{heading}"><h3>{heading}</h3>'
            f'<div class="daily-drivers-grid">{"".join(tables)}</div>'
            f'<div class="daily-drivers-footer"><span>{escape(tr("Wpływ USD/PLN"))} <strong>{fx_text}</strong></span>'
            f'<span>{escape(tr("Dzienna zmiana w PLN"))} <strong>{total_text}</strong></span></div>'
            f'<small class="daily-drivers-note">{escape(note)}</small></section>')


def summary(positions, fx, overall=False):
    value, cost = positions["Wartość"].sum(), positions["Kapitał"].sum()
    scope = "all" if overall else str(positions["Portfel"].iloc[0])
    change = daily_change(positions)
    daily_color = "neutral" if change is None else "up" if change >= 0 else "down"
    return_color = "up" if value >= cost else "down"
    quote, error = fx
    rate = round(quote["price"], 4) if quote else None
    converted = cost * rate if rate is not None else None
    converted_text = "— PLN" if converted is None or not math.isfinite(converted) else f"{converted:,.2f} PLN"
    market_pln = value * rate if rate is not None else None
    market_pln_text = "— PLN" if market_pln is None or not math.isfinite(market_pln) else f"{market_pln:,.2f} PLN"
    # Native wrapping avoids four squeezed columns on phones and tablets.
    with st.container(horizontal=True, horizontal_alignment="center"):
        with st.container(width=260):
            st.metric(tr("Łączna wartość" if overall else "Wartość rynkowa"), f"${value:,.2f}",
                      delta=market_pln_text, delta_color="off", delta_arrow="off",
                      help=tr("Wartość w USD przeliczona po bieżącym kursie z pola USD/PLN.") if quote else tr(error))
        with st.container(width=260, key=f"change-{daily_color}-daily-{scope}"):
            daily_metric(st, positions)
        with st.container(width=260, key=f"change-{return_color}-return-{scope}"):
            return_metric(st, positions)
        with st.container(width=260):
            st.metric(tr("Zainwestowany kapitał"), f"${cost:,.2f}", delta=converted_text,
                      delta_color="off", delta_arrow="off",
                      help=tr("Zainwestowany kapitał w USD przeliczony po bieżącym kursie z pola USD/PLN.") if quote else tr(error))
        if overall:
            with st.container(width=260):
                delta = None
                help_text = tr("1 USD w PLN. Zmiana względem poprzedniego zamknięcia rynku walutowego.")
                if quote:
                    previous = quote.get("previous_close")
                    if previous:
                        amount = quote["price"] - previous
                        delta = f'{(quote["price"] / previous - 1) * 100:+.2f}% · {amount:+.4f} PLN'
                    help_text += " · Yahoo Finance · " + display_time(quote["timestamp"])
                else:
                    help_text = tr(error)
                st.metric("USD/PLN", "—" if quote is None else f'{quote["price"]:.4f} PLN',
                          delta=delta, help=help_text)
                render_daily_history(load_daily_history("PLN=X"), "USD/PLN", "USD/PLN", "usd-pln-history",
                                     precision=4)
    if change is not None:
        render_daily_drivers(positions, quote)


def mobile_holdings(part, visible_columns):
    if not visible_columns:
        st.html('<div class="mobile-holdings">' + escape(tr("Wszystkie kolumny ukryte. Wybierz kolumny w menu Widoczne kolumny.")) + '</div>')
        return
    columns = [column_metadata(column) for column in visible_columns]
    cards = []
    for _, row in part.iterrows():
        fields = []
        for column in columns:
            value = row[column["id"]]
            color = ""
            if pd.isna(value):
                text = "—"
            elif column["kind"] == "text":
                text = str(value)
            elif not math.isfinite(float(value)):
                text = "—"
            else:
                sign = "+" if column["signed"] and value >= 0 else ""
                digits = 1 if column["kind"] == "weight" else 2
                prefix = "$" if column["kind"] == "money" else ""
                suffix = "%" if column["kind"] in ("percent", "weight") else ""
                text = f"{sign}{prefix}{value:,.{digits}f}{suffix}"
                if column["signed"]:
                    color = "up" if value >= 0 else "down"
            fields.append(f'<div><dt>{escape(column["label"])}</dt><dd class="{color}">{escape(text)}</dd></div>')
        cards.append('<article class="holding-card"><dl class="holding-details">' + "".join(fields) + '</dl></article>')
    st.html('<div class="mobile-holdings">' + "".join(cards) + '</div>')


def render_extended(part, quotes, name):
    now = datetime.now(timezone.utc)
    sessions = {symbol: extended_session(quotes.get(symbol, {}), now) for symbol in part["Ticker"].unique()}
    st.markdown('<div class="section-label">After-hours &amp; stuff</div>', unsafe_allow_html=True)
    st.markdown("##### Tickers")
    cards = []
    for symbol in part["Ticker"].unique():
        rows = []
        active = quote_regular_active(quotes.get(symbol, {}), now)
        selected = sessions[symbol]
        for label, field in (("Pre-market", "pre_market"), ("After-hours", "after_hours")):
            if selected is not None and field != selected:
                continue
            value = extended_value(quotes.get(symbol, {}), field, now)
            if value:
                percent = value.get("change_percent")
                css = "neutral" if percent is None else ("up" if percent >= 0 else "down")
                change = "—" if percent is None else f"{percent:+.2f}%"
                stamp = display_time(value["timestamp"])
                stamp += " · " + tr("Yahoo · świeca 1 min (dane zastępcze)" if value.get("source") == "yahoo_1m"
                                       else "Yahoo · cena sesji")
                row = f'<strong>${value["price"]:,.2f}</strong> <span class="{css}">{change}</span>'
            else:
                row = "—"
                stamp = tr("Trwa sesja regularna — notowania rozszerzone są ukryte." if active else
                           "Brak dostępnych notowań")
            rows.append(f'<div class="extended-row"><span>{label}</span><div>{row}</div></div>'
                        f'<div class="extended-time">{stamp}</div>')
        portfolios = " · ".join(portfolio_label(value) for value in part.loc[part["Ticker"] == symbol, "Portfel"].drop_duplicates())
        cards.append(f'<article class="holding-card"><strong>{escape(symbol)}</strong>'
                     f'<div class="extended-time">{escape(portfolios)}</div>{"".join(rows)}</article>')
    st.html('<div class="extended-grid">' + "".join(cards) + '</div>')
    cash_session = next((quote["regular_session"] for quote in quotes.values() if quote.get("regular_session")), None)
    benchmark_tickers = tuple(ticker for _, ticker in BENCHMARK_CHARTS.values())
    with parallel_loads({
        "benchmarks": lambda: load_benchmarks(cash_session),
        **{symbol: lambda symbol=symbol: load_daily_history(symbol) for symbol in benchmark_tickers},
        "vix": load_vix, "crude_oil": load_crude_oil,
        "context": load_market_context, "sentiment": load_sentiment,
        **{symbol: lambda symbol=symbol: load_daily_history(symbol)
           for symbol in ("^VIX", "CL=F", "^TNX")},
    }) as pending:
        st.markdown("##### Indexes")
        render_benchmarks(cash_session, pending["benchmarks"].result,
                          {ticker: pending[ticker].result for ticker in benchmark_tickers})
        st.markdown("##### Others")
        with st.container(horizontal=True, horizontal_alignment="center"):
            render_vix(pending["vix"].result, pending["^VIX"].result())
            render_crude_oil(pending["crude_oil"].result, pending["CL=F"].result())
            render_market_context(pending["context"].result, cash_session, pending["^TNX"].result())
        render_sector_map()
        render_macro_calendar()
        with st.container(horizontal_alignment="center"):
            render_sentiment(name, pending["sentiment"].result)


def render_sector_map():
    with st.expander(tr("Mapa sektorów S&P 500"), expanded=True, key="sector-map", on_change="rerun") as section:
        if not section.open:
            return
        data = load_sectors()
        cards = []
        for symbol, label in SECTORS.items():
            quote = data.get(symbol)
            color = "neutral" if not quote else "up" if quote["change"] >= 0 else "down"
            value = "—" if not quote else f'{quote["change"]:+.2f}%'
            stamp = "" if not quote else f' · {quote["day"]:%d.%m.%Y}'
            cards.append(f'<div class="sector-tile {color}"><strong>{escape(tr(label))}</strong>'
                         f'<span>{value}</span><small>{symbol}{stamp}</small></div>')
        st.html('<div class="sector-map">' + "".join(cards) + '</div>')


def render_macro_calendar():
    with st.expander(tr("Kalendarz makro USA · najbliższe 45 dni"), expanded=True, key="macro-calendar", on_change="rerun") as section:
        if not section.open:
            return
        snapshot = load_macro_calendar()
        events = upcoming_macro(snapshot["events"])
        if snapshot["failures"]:
            st.warning(tr("Niepełny kalendarz makro — niedostępne źródła: ") + ", ".join(snapshot["failures"]))
        if not events:
            st.info(tr("Brak dostępnych nadchodzących wydarzeń makro."))
            return
        cards = []
        for event in events:
            stamp = display_time(event["when"]) if event["when"] else event["day"].strftime("%d.%m.%Y") + " · " + tr("godzina niepotwierdzona")
            cards.append(f'<article class="holding-card"><strong>{escape(tr(event["title"]))}</strong>'
                         f'<div class="extended-row">{escape(stamp)}</div>'
                         f'<div class="extended-time">{escape(event["source"])}</div></article>')
        st.html('<div class="extended-grid">' + "".join(cards) + '</div>')


def render_market_context(data_loader=load_market_context, cash_session=None, us10y_history=()):
    data = data_loader()
    us10y = data.get("us10y")
    with st.container(width=260):
        delta = None
        help_text = tr("Rentowność obligacji skarbowych USA 10Y. Zmiana w punktach bazowych względem poprzedniego odczytu dziennego.")
        if us10y:
            if us10y["previous"] is not None:
                delta = f'{(us10y["value"] - us10y["previous"]) * 100:+.2f} ' + tr("pb")
            help_text += f' · Yahoo Finance (^TNX) · {us10y["as_of"]:%Y-%m-%d}'
        else:
            help_text = tr("Dane chwilowo niedostępne.")
        st.metric("US 10Y", "—" if not us10y else f'{us10y["value"]:.3f}%',
                  delta=delta, delta_color="normal", help=help_text)
        render_daily_history(us10y_history, "US 10Y", "US 10Y (%)", "us10y-history", precision=3)
    breadth = data.get("breadth")
    with st.container(width=260):
        help_text = tr("Rosnące / spadające walory na NYSE, Nasdaq i AMEX. Zmiana poniżej to bilans: rosnące minus spadające, nie zmiana względem wczoraj. Finviz nie podaje czasu samego odczytu; dane mogą być opóźnione.")
        if breadth:
            value = f'{breadth["advancing"]:,} / {breadth["declining"]:,}'
            delta = f'{breadth["advancing"] - breadth["declining"]:+,} ' + tr("bilans")
            help_text += " · Finviz · " + tr("pobrano ") + display_time(breadth["fetched_at"])
        else:
            value, delta = "—", None
            help_text = tr("Dane chwilowo niedostępne.")
        st.metric(tr("Rynek · rosnące / spadające"), value, delta=delta,
                  delta_color="normal", help=help_text)
        render_breadth_history(breadth, cash_session)
    put_call = data.get("put_call")
    with st.container(width=260):
        help_text = tr("Dzienny stosunek wolumenu opcji put do call na akcje. Equity Put/Call Ratio, bez opcji indeksowych i ETF. Wartość bez zmiany dziennej.")
        if put_call:
            help_text += f' · Cboe · {put_call["as_of"]:%Y-%m-%d}'
        else:
            help_text = tr("Dane chwilowo niedostępne.")
        st.metric("Equity Put/Call", "—" if not put_call else f'{put_call["value"]:.2f}', help=help_text)


def render_breadth_history(breadth, cash_session):
    now = datetime.now(EXCHANGE_ZONE)
    try:
        history = load_breadth_history(breadth, cash_session, now=now)
    except (OSError, sqlite3.Error):
        configure_logs()[1].exception("Could not store or load market breadth history")
        st.caption(tr("Historia szerokości rynku jest chwilowo niedostępna."))
        return
    if not history:
        st.caption(tr("Historia pojawi się po pierwszym odczycie zapisanym w ostatnich 30 minutach sesji USA."))
        return

    label = tr("Rosnące / spadające · ostatnie 14 dni")
    st.caption(label)
    today = now.date()
    # Leave space for the points at the ends of the plot.
    bounds = (today - timedelta(days=BREADTH_HISTORY_DAYS), today)
    domain = [{"year": day.year, "month": day.month, "date": day.day, "hours": 12, "utc": True}
              for day in bounds]
    advancing_label, declining_label = tr("Rosnące walory"), tr("Spadające walory")
    history = pd.DataFrame(history).rename(columns={"advancing": advancing_label, "declining": declining_label})
    spec = {
        "height": 105,
        "transform": [{"fold": [advancing_label, declining_label], "as": ["series", "count"]}],
        "mark": {"type": "line", "point": True},
        "encoding": {
            "x": {"field": "day", "type": "temporal", "title": None, "scale": {"type": "utc", "domain": domain},
                  "axis": {"format": "%d.%m", "tickCount": {"interval": "day", "step": 3}, "labelAngle": 0}},
            "y": {"field": "count", "type": "quantitative", "title": None,
                  "scale": {"zero": False}, "axis": {"tickCount": 4, "format": ",d"}},
            "color": {"field": "series", "type": "nominal", "title": None,
                      "scale": {"domain": [advancing_label, declining_label],
                                "range": ["#168047", "#c33935"]},
                      "legend": {"orient": "bottom", "columns": 1}},
            "tooltip": [{"field": "day", "type": "temporal", "title": tr("Data sesji"),
                         "formatType": "utc", "format": "%d.%m.%Y"},
                        {"field": "net", "type": "quantitative", "title": tr("Bilans rynku"), "format": "+,d"},
                        {"field": advancing_label, "type": "quantitative", "format": ",d"},
                        {"field": declining_label, "type": "quantitative", "format": ",d"}],
        },
    }
    st.vega_lite_chart(history, spec, width="stretch", key="breadth-history", alt=label)


def render_vix(data_loader=load_vix, history=()):
    with st.container(width=260):
        vix, vix_error = data_loader()
        delta = None
        help_text = tr("Indeks zmienności Cboe VIX. Zmiana względem poprzedniego zamknięcia. Wzrost oznacza większą oczekiwaną zmienność.")
        if vix:
            previous = vix.get("previous_close")
            if previous:
                amount = vix["price"] - previous
                delta = f'{(vix["price"] / previous - 1) * 100:+.2f}% · {amount:+.2f} ' + tr("pkt")
            help_text += " · Yahoo Finance (^VIX) · " + display_time(vix["timestamp"])
        else:
            help_text = tr(vix_error)
        st.metric(tr("VIX · indeks strachu"), "—" if not vix else f'{vix["price"]:.2f}',
                  delta=delta, delta_color="normal", help=help_text)
        render_daily_history(history, "VIX", f'VIX ({tr("pkt")})', "vix-history")


def render_daily_history(history, name, value_label, key, *, precision=2, source=None):
    if not history:
        st.caption(tr("Brak danych z ostatnich 14 dni."))
        return

    label = name + " · " + tr("ostatnie 14 dni")
    st.caption(label, help=source)
    spec = {
        "height": 105,
        "mark": {"type": "line", "point": True},
        "encoding": {
            "x": {"field": "day", "type": "temporal", "title": None, "scale": {"type": "utc"},
                  "axis": {"format": "%d.%m", "tickCount": "day", "labelAngle": 0}},
            "y": {"field": "level", "type": "quantitative", "title": None,
                  "scale": {"zero": False}, "axis": {"tickCount": 4}},
            "tooltip": [{"field": "day", "type": "temporal", "title": tr("Data sesji"),
                         "formatType": "utc", "format": "%d.%m.%Y"},
                        {"field": "level", "type": "quantitative", "title": value_label, "format": f",.{precision}f"}],
        },
    }
    st.vega_lite_chart(pd.DataFrame(history), spec, width="stretch", key=key, alt=label)


def render_crude_oil(data_loader=load_crude_oil, history=()):
    with st.container(width=260):
        quote, error = data_loader()
        delta = None
        help_text = tr("Kontrakty na ropę WTI w USD za baryłkę. Zmiana względem poprzedniego zamknięcia. Dane mogą być opóźnione.")
        if quote:
            changes = []
            if quote["change_percent"] is not None:
                changes.append(f'{quote["change_percent"]:+.2f}%')
            if quote["change"] is not None:
                changes.append(f'{quote["change"]:+.2f} USD')
            delta = " · ".join(changes) or None
            if quote["change"] == 0:
                delta = 0
            help_text += " · Yahoo Finance (CL=F) · " + display_time(quote["timestamp"])
        else:
            help_text = tr(error)
        st.metric("Crude Oil WTI (CL.F)", "—" if not quote else f'${quote["price"]:,.2f}',
                  delta=delta, help=help_text)
        if not quote:
            st.caption(tr(error))
        render_daily_history(history, "WTI", tr("WTI (USD za baryłkę)"), "wti-history")


def render_sentiment(name, data_loader=load_sentiment):
    data, error = data_loader()
    with st.container(border=True, width=440):
        st.markdown("**Fear & Greed Index · FearGreedFlow**")
        if data:
            st.echarts_chart({
                "animationDuration": 600,
                "animationDurationUpdate": 500,
                "series": [{
                    "type": "gauge", "min": 0, "max": 100, "splitNumber": 4,
                    "startAngle": 225, "endAngle": -45,
                    "center": ["50%", "48%"], "radius": "78%",
                    "axisLine": {"lineStyle": {"width": 22, "color": [
                        [0.25, "#d85d68"], [0.45, "#eba45c"], [0.55, "#dfc660"],
                        [0.75, "#91b77c"], [1, "#459e88"]]}},
                    "pointer": {"length": "57%", "width": 5, "itemStyle": {"color": "#283747"}},
                    "anchor": {"show": True, "showAbove": True, "size": 12,
                               "itemStyle": {"color": "#283747", "borderColor": "#ffffff", "borderWidth": 3}},
                    "axisTick": {"show": False},
                    "splitLine": {"length": 12, "distance": -22,
                                  "lineStyle": {"width": 2, "color": "#ffffff"}},
                    "axisLabel": {"distance": 13, "color": "#68717b", "fontSize": 12},
                    "title": {"offsetCenter": [0, "68%"], "fontSize": 15, "color": "#68717b"},
                    "detail": {"valueAnimation": True, "formatter": "{value} / 100",
                               "offsetCenter": [0, "42%"], "fontSize": 27,
                               "fontWeight": 700, "color": "#283747"},
                    "data": [{"value": round(data["score"], 1), "name": tr(data["rating"])}],
                }],
            }, width="stretch", height=340, renderer="svg", key=f"sentiment-gauge-{name}",
                alt=f'Fear & Greed: {data["score"]:.1f}/100 · {tr(data["rating"])}')
            st.caption(tr("Aktualizacja źródła: ") + display_time(data["timestamp"]))
        else:
            st.caption(tr(error))
        st.link_button(tr("Źródło: FearGreedFlow"), SENTIMENT_SOURCE_URL)


def render_benchmarks(regular_session, data_loader=None, history_loaders=None):
    quotes, errors = data_loader() if data_loader else load_benchmarks(regular_session)
    now = datetime.now(timezone.utc)
    for (name, index, future), column in zip(BENCHMARKS, st.columns(len(BENCHMARKS)), strict=True):
        rows = []
        show_future = index in quotes and quote_regular_active(quotes[index], now) is False
        for label, symbol, visible in (("Cash", index, True), ("Futures", future, show_future)):
            quote = quotes.get(symbol) if visible else None
            if quote:
                change = quote.get("change_percent")
                color = "neutral" if change is None else "up" if change >= 0 else "down"
                percent = "—" if change is None else f"{change:+.2f}%"
                value = f'<strong>{quote["price"]:,.{quote["precision"]}f}</strong> <span class="{color}">{percent}</span>'
                stamp = display_time(quote["timestamp"]) + " · " + escape(quote["symbol"])
                if quote["delayed"]:
                    stamp += " · " + tr("Dane opóźnione")
            else:
                value = "—"
                stamp = (tr("Futures ukryte podczas sesji regularnej indeksu.")
                         if symbol == future and index in quotes and quote_regular_active(quotes[index], now) is True
                         else tr("Brak dostępnych notowań"))
            rows.append(f'<div class="extended-row"><span>{label}</span><div>{value}</div></div>'
                        f'<div class="extended-time">{stamp}</div>')
        with column:
            st.html(f'<article class="holding-card"><strong>{escape(name)}</strong>{"".join(rows)}</article>')
            if history_loaders is not None:
                chart_name, ticker = BENCHMARK_CHARTS[index]
                render_daily_history(history_loaders[ticker](), chart_name, f'{chart_name} ({tr("pkt")})',
                                     f"benchmark-history-{index}", source=f"Yahoo Finance ({ticker})")
    if errors:
        unavailable = [name + " " + label for name, cash, future in BENCHMARKS
                       for label, symbol in (("Cash", cash), ("Futures", future)) if symbol in errors]
        st.caption(tr("Brak dostępu do notowań: ") + ", ".join(unavailable))


def render_data_notes():
    if not show_info:
        return
    st.caption(tr("Mapa sektorów: zmiany dzienne ETF-ów Select Sector SPDR względem poprzedniego zamknięcia, nie wagi kapitalizacji sektorów. Źródło: Yahoo Finance. Dane mogą być opóźnione."))
    st.caption(tr("Kalendarz makro: Fed, BEA i BLS; przy braku BLS pomocniczo Forex Factory (bieżący tydzień). Brak potwierdzonej godziny nie jest zastępowany szacunkiem. Terminy mogą się zmienić."))
    st.caption(tr("Bezpośrednie ceny Yahoo; przy braku ceny oznaczone świece 1-minutowe. Czas w CET/CEST (Europe/Warsaw). "
                  "Pre-market: zmiana względem poprzedniego zamknięcia. After-hours: względem zamknięcia tej sesji. "
                  "Tylko dane z bieżącego dnia giełdowego; mogą być opóźnione. Wycena portfela używa cen sesji regularnej."))
    st.caption(tr("Źródło: Investing.com — US Tech 100 Cash, US 500 Cash i powiązane futures CME. Wartości w punktach, czas CET/CEST. Futures podczas regularnej sesji rynku akcji: —. Dane mogą być opóźnione."))
    st.caption(tr("Dywidenda na akcję i suma są kwotami brutto. Suma to szacunek dla obecnej liczby akcji, nie potwierdzenie prawa do wypłaty. Ex-dividend to data odcięcia prawa do dywidendy. Terminy wyników mogą być szacunkowe. — oznacza brak danych."))
    st.caption(tr("Kalendarz wyników i dywidend — wszystkie portfele") + ": " + tr("Pobierane raz przy otwarciu aplikacji"))
    st.caption(tr("Najnowsze nagłówki z ostatnich 7 dni · do 10 wiadomości · Yahoo Finance"))
    st.caption(tr("odświeżanie co 10 min") + " · " + tr("artykuły mogą wymagać subskrypcji"))
    st.caption("Fear & Greed: " + tr("0 = skrajny strach, 100 = skrajna chciwość."))
    st.caption(tr("Pozycje zapisane lokalnie w portfolio.json. Dane nie są synchronizowane z brokerem."))


def render_portfolio(name, positions, total, fx):
    part = positions.loc[positions["Portfel"] == name].copy()
    if part.empty:
        st.info(tr("Ten portfel nie ma pozycji."))
        return
    value = part["Wartość"].sum()
    with st.container():
        st.markdown(
            f'<div class="portfolio-name">{escape(portfolio_label(name))}</div>' +
            tr(f'<div class="portfolio-sub">{len(part)} pozycje · {value / total:.1%} całości · USD</div>'),
            unsafe_allow_html=True,
        )
        summary(part, fx)
        st.markdown(tr('<div class="section-label">Posiadane akcje</div>'), unsafe_allow_html=True)
        visible_columns = column_settings(name)
        part["Udział %"] = part["Wartość"] / value * 100
        mobile_holdings(part, visible_columns)
        with st.container(key=f"desktop-holdings-{name}"):
            render_holdings_table(part, visible_columns, name)
        with st.expander(tr("Struktura portfela"), key=f"structure-{name}", on_change="rerun") as allocation:
            if allocation.open:
                render_allocation(part, name)


def column_settings(name):
    key = f"visible-columns-{name}-{language()}"
    column_labels = {c: tr(LABELS.get(c, c)) for c in COLUMNS}
    try:
        saved = columns_for(name)
    except (ValueError, OSError) as exc:
        st.warning(tr(f"Nie można odczytać układu kolumn: {exc}"))
        saved = list(COLUMNS)
    # Visibility is a set, represented in stable option order. Dragging changes
    # only the persisted display order, never this widget's value/order.
    selected = [c for c in COLUMNS if c in saved]
    if st.session_state.get(key) != selected:
        st.session_state[key] = selected

    def persist(reset_order=False):
        if not is_authenticated():
            return
        try:
            chosen = st.session_state[key]
            current = columns_for(name)
            ordered = ([*chosen] if reset_order else
                       [c for c in current if c in chosen] + [c for c in chosen if c not in current])
            save_columns(name, ordered)
            st.session_state.pop(f"layout-error-{name}", None)
        except (ValueError, OSError) as exc:
            configure_logs()[1].exception("Could not save table layout")
            st.session_state[f"layout-error-{name}"] = str(exc)

    def reset():
        if not is_authenticated():
            return
        st.session_state[key] = list(COLUMNS)
        persist(reset_order=True)

    def add_column():
        if not is_authenticated():
            return
        chosen = st.session_state.get(f"add-column-choice-{name}-{language()}")
        if chosen and chosen not in st.session_state[key]:
            st.session_state[key] = [*st.session_state[key], chosen]
            persist()


    with st.popover(tr("⚙ Widoczne kolumny")):
        hidden = [c for c in COLUMNS if c not in st.session_state[key]]
        if hidden:
            st.selectbox(tr("Dodaj kolumnę"), hidden, key=f"add-column-choice-{name}-{language()}",
                         format_func=column_labels.__getitem__)
            st.button(tr("＋ Dodaj wybraną kolumnę"), key=f"add-column-{name}", on_click=add_column)
        else:
            st.caption(tr("Wszystkie dostępne kolumny są już widoczne."))
        st.multiselect(tr("Widoczne kolumny — usuń × lub wybierz z listy"), COLUMNS, key=key, on_change=persist,
                       format_func=column_labels.__getitem__)
        st.caption(tr("Zmiany zapisują się automatycznie, osobno dla każdego portfela. "
                   "Wybrany układ jest wspólny dla urządzeń korzystających z tej instalacji."))
        st.button(tr("Przywróć wszystkie kolumny"), key=f"reset-columns-{name}", on_click=reset)
        if f"layout-error-{name}" in st.session_state:
            st.error(tr("Nie zapisano układu: " + st.session_state[f"layout-error-{name}"]))
    return saved


def render_holdings_table(part, visible_columns, name):
    if not visible_columns:
        st.info(tr("Wszystkie kolumny ukryte. Wybierz kolumny w menu Widoczne kolumny."))
        return
    render_table(part, visible_columns, name, display_name=portfolio_label(name))


def allocation_colors(symbols):
    assigned = dict(COLORS)
    used = set(COLORS.values())
    for symbol in sorted(set(symbols) - set(COLORS)):
        hue = int.from_bytes(sha256(symbol.encode()).digest()[:2], "big") * 360 / 65536
        color = f"hsl({hue:.3f}, 58%, 51%)"
        while color in used:
            hue = (hue + 137.508) % 360
            color = f"hsl({hue:.3f}, 58%, 51%)"
        assigned[symbol] = color
        used.add(color)
    return [assigned[symbol] for symbol in symbols]


def render_allocation(part, name):
    chart = part[["Ticker", "Wartość", "Udział %"]].copy()
    chart["weight"] = chart["Udział %"] / 100
    symbols = part["Ticker"].tolist()
    colors = allocation_colors(symbols)
    spec = {
        # Fit horizontally without letting the legend shrink the plot vertically.
        # Keep room above the fixed-radius arc, including its border.
        "height": 320,
        "autosize": {"type": "fit-x", "contains": "padding"},
        "padding": {"top": 20, "right": 12, "bottom": 12, "left": 12},
        "background": "transparent", "view": {"stroke": None},
        "encoding": {
            "theta": {"field": "Wartość", "type": "quantitative", "stack": True},
            "detail": {"field": "Ticker", "type": "nominal"},
            "color": {"field": "Ticker", "type": "nominal", "title": None,
                      "scale": {"domain": symbols, "range": colors},
                      "legend": {"orient": "bottom", "columns": 2}},
            "order": {"field": "Ticker", "type": "nominal"},
            "tooltip": [{"field": "Ticker", "type": "nominal", "title": tr("Symbol")},
                        {"field": "Wartość", "type": "quantitative", "title": tr("Wartość"), "format": "$,.2f"},
                        {"field": "weight", "type": "quantitative", "title": tr("Udział"), "format": ".1%"}],
        },
        "layer": [
            {"mark": {"type": "arc", "innerRadius": 65, "outerRadius": 115,
                      "stroke": "#ffffff", "strokeWidth": 2}},
            {"mark": {"type": "text", "radius": 90, "fontSize": 13},
             "encoding": {"text": {"field": "weight", "type": "quantitative", "format": ".1%"},
                          "color": {"value": "white"}}},
        ],
    }
    st.vega_lite_chart(chart, spec, width="stretch", key=f"allocation-{name}",
                       alt=tr("Struktura portfela"))

with st.sidebar:
    st.markdown(tr("### Ustawienia portfela"))
    logout_button()
    st.divider()
    st.markdown(tr("**Dane rynkowe**"))
    auto_refresh = st.toggle(tr("Odświeżaj co minutę"), value=True)
    show_info = st.checkbox("Info", value=False, key="show-info")


def add_position_form(records):
    if st.session_state.pop("purchase-form-reset", False):
        for key in ("add-symbol", "add-shares", "add-price"):
            st.session_state.pop(key, None)
    with st.popover(tr("＋ Dodaj pozycję")):
        st.caption(tr("Nowy symbol tworzy pozycję. Dla istniejącego dopisujemy akcje i przeliczamy średnią ważoną."))
        with st.form("add-position", clear_on_submit=False):
            labels = {p: portfolio_label(p) for p in PORTFOLIOS}
            portfolio = st.selectbox(tr("Portfel"), PORTFOLIOS, key="add-portfolio", format_func=labels.__getitem__)
            symbol = st.text_input(tr("Symbol Yahoo Finance"), max_chars=25, placeholder="AAPL", key="add-symbol")
            shares = st.number_input(tr("Liczba kupionych akcji"), min_value=0.0, value=0.0,
                                     step=1.0, format="%.4f", key="add-shares")
            price = st.number_input(tr("Cena zakupu jednej akcji (USD)"), min_value=0.0, value=0.0,
                                    step=0.01, format="%.4f", key="add-price")
            submitted = st.form_submit_button(tr("Dodaj zakup"), width="stretch")
        if submitted:
            require_login()
            try:
                purchase = validate_position({"portfolio": portfolio, "symbol": symbol,
                                              "shares": shares, "average_price": price})
                known = next((r for r in records if r["symbol"] == purchase["symbol"]), None)
                purchase["name"] = known["name"] if known else lookup_company(purchase["symbol"])
                result = add_position(purchase)
            except (ValueError, OSError) as exc:
                configure_logs()[1].warning("Could not add purchase: %s", exc)
                st.error(tr(str(exc)))
            else:
                st.session_state["purchase-form-reset"] = True
                st.session_state.position_updated = tr("Dodano zakup: ") + f'{result["symbol"]} · {portfolio_label(result["portfolio"])}.'
                st.rerun()


def edit_position_form(records):
    selected = st.session_state.get("edit-selected")
    if not isinstance(selected, int) or not 0 <= selected < len(records):
        st.session_state["edit-selected"] = 0
    with st.popover(tr("✎ Edytuj pozycję")):
        labels = {i: f'{portfolio_label(record["portfolio"])} · {record["symbol"]} · {record["name"]}'
                  for i, record in enumerate(records)}
        index = st.selectbox(tr("Wybierz pozycję"), range(len(records)), index=None,
                             format_func=labels.__getitem__,
                             key="edit-selected")
        original = records[index]
        identity = "edit-" + str(tuple(original.values()))
        st.caption(tr("Podaj łączną liczbę posiadanych akcji i aktualną średnią cenę zakupu. Zapis zastępuje poprzednie wartości."))
        with st.form(identity):
            shares = st.number_input(tr("Liczba akcji"), min_value=0.0, value=original["shares"],
                                     step=1.0, format="%.4f", key=identity+"-shares")
            average = st.number_input(tr("Średnia cena zakupu (USD)"), min_value=0.0, value=original["average_price"],
                                      step=0.01, format="%.4f", key=identity+"-average")
            submitted = st.form_submit_button(tr("Zapisz zmiany"), width="stretch")
        if submitted:
            try:
                update_position(original, {**original, "shares": shares, "average_price": average})
            except (ValueError, OSError) as exc:
                configure_logs()[1].exception("Could not update portfolio position")
                st.error(tr(str(exc)))
            else:
                st.session_state.position_updated = f'Zapisano zmiany: {original["symbol"]} · {portfolio_label(original["portfolio"])}.'
                st.rerun()
        with st.expander(tr("Usuń tę pozycję")):
            st.caption(tr("Usunięta zostanie cała pozycja: ") + f'{original["symbol"]} · {portfolio_label(original["portfolio"])}.')
            if st.button(tr("Usuń z portfela"), key=identity + "-delete"):
                require_login()
                try:
                    remove_position(original)
                except (ValueError, OSError) as exc:
                    configure_logs()[1].warning("Could not remove holding: %s", exc)
                    st.error(tr(str(exc)))
                else:
                    st.session_state.position_updated = tr("Usunięto pozycję: ") + f'{original["symbol"]} · {portfolio_label(original["portfolio"])}.'
                    st.rerun()


def rename_portfolio_form():
    with st.popover(tr("Nazwy portfeli")):
        labels = {p: portfolio_label(p) for p in PORTFOLIOS}
        portfolio = st.selectbox(tr("Portfel"), PORTFOLIOS, key="rename-portfolio", format_func=labels.__getitem__)
        current = portfolio_label(portfolio)
        with st.form(f"rename-form-{portfolio}"):
            name = st.text_input(tr("Nowa nazwa portfela"), value=current, max_chars=40,
                                 key=f"rename-name-{portfolio}-{current}")
            submitted = st.form_submit_button(tr("Zapisz nazwę"))
        if submitted:
            require_login()
            try:
                rename_portfolio(portfolio, name, current)
            except (ValueError, OSError) as exc:
                st.error(tr(str(exc)))
            else:
                st.session_state.position_updated = tr("Zapisano nazwę portfela.")
                st.rerun()


@st.fragment(run_every=60 if auto_refresh else None)
def dashboard():
    require_login()
    try:
        records = load_positions()
        st.session_state["portfolio-names"] = load_portfolio_names()
    except (ValueError, OSError) as exc:
        configure_logs()[1].exception("Could not read portfolio data")
        st.error(tr(f"Nie można odczytać portfolio.json: {exc}"))
        return
    with st.container(horizontal=True, horizontal_alignment="right", vertical_alignment="center"):
        if st.button(tr("↻ Odśwież notowania"), width="content"):
            load_quotes.clear()
            load_usd_pln.clear()
            load_vix.clear()
            load_daily_history.clear()
            load_crude_oil.clear()
            load_market_context.clear()
            load_sectors.clear()
            load_macro_calendar.clear()
            load_benchmarks.clear()
            load_sentiment.clear()
        if records:
            edit_position_form(records)
        else:
            st.button(tr("✎ Edytuj pozycję"), disabled=True)
        add_position_form(records)
        rename_portfolio_form()
        logout_button()
        language_selector()
    st.markdown(tr('<div class="masthead"><div class="brand">My<span>Portfolio</span> manager</div>'
                '<div class="masthead-note">AKCJE USA &nbsp; / &nbsp; USD</div></div>'), unsafe_allow_html=True)
    st.title("MyPortfolio manager")
    if "position_updated" in st.session_state:
        st.success(tr(st.session_state.pop("position_updated")))
    if not records:
        st.info(tr("Portfele są puste. Dodaj pierwszą pozycję przyciskiem u góry."))
        return
    symbols = tuple(sorted({r["symbol"] for r in records}))
    calendar_positions = pd.DataFrame(records).rename(columns={
        "portfolio": "Portfel", "name": "Spółka", "symbol": "Ticker", "shares": "Akcje",
    })
    with st.spinner(tr("Pobieranie notowań…")):
        quotes, errors = load_quotes(symbols)
    if errors:
        if set(st.session_state.get("last_quotes", {})) != set(symbols):
            st.error(tr("Nie udało się pobrać wszystkich cen. Spróbuj odświeżyć notowania."))
            for symbol, error in errors.items():
                st.caption(tr(f"{symbol}: {error}"))
            render_calendar(calendar_positions, "all-portfolios", symbols)
            render_extended(calendar_positions, quotes, "all-portfolios")
            render_news(symbols)
            render_data_notes()
            return
        st.warning(tr("Błąd aktualizacji: " + ", ".join(errors)
                   + ". Wyświetlane są ostatnie kompletne dane; sprawdź czas pobrania na dole."))
        quotes = st.session_state.last_quotes
    else:
        st.session_state.last_quotes = quotes

    positions = value_positions(quotes, records)
    value = positions["Wartość"].sum()
    fetched = min(q["fetched_at"] for q in quotes.values())
    strip = []
    for symbol, quote in quotes.items():
        previous = quote.get("previous_close")
        change = (quote["price"] / previous - 1) * 100 if previous else None
        color = "neutral" if change is None else ("up" if change >= 0 else "down")
        change_text = "—" if change is None else f"{change:+.2f}%"
        strip.append(f'<div class="quote">{ticker_logo(symbol)}<strong>{escape(symbol)}</strong>'
                     f'<span class="quote-price">{quote["price"]:.2f}</span>'
                     f'<span class="{color}">{change_text}</span></div>')
    st.markdown(tr('<div class="quote-strip">' + "".join(strip) + '</div>'), unsafe_allow_html=True)
    st.markdown(tr('<div class="section-label">Wszystkie portfele</div>'), unsafe_allow_html=True)
    fx = load_usd_pln()
    summary(positions, fx, overall=True)
    if positions["Poprzednie zamknięcie"].isna().any():
        st.info(tr("Brak poprzedniego zamknięcia dla części spółek. Ich zmiana dzienna i suma portfela są niedostępne."))
    elif positions["Sesja"].nunique() != 1:
        st.info(tr("Notowania dotyczą różnych sesji. Łączna zmiana dzienna jest niedostępna do czasu aktualizacji."))
    # Client-side switching avoids recreating the header and losing scroll.
    # Per-symbol caches share market data between both rendered portfolios.
    long_tab, xtb_tab = st.tabs([portfolio_label(portfolio) for portfolio in PORTFOLIOS])
    with long_tab:
        render_portfolio("Erste-DM", positions, value, fx)
    with xtb_tab:
        render_portfolio("XTB", positions, value, fx)

    render_calendar(calendar_positions, "all-portfolios", symbols)
    render_extended(calendar_positions, quotes, "all-portfolios")
    render_news(symbols)

    with st.expander(tr("Źródło i czas notowań")):
        st.dataframe(pd.DataFrame([
            {"Ticker": symbol, "Kurs (USD)": q["price"],
             "Czas notowania (CET/CEST)": display_time(q["timestamp"])}
            for symbol, q in quotes.items()
        ]).rename(columns=tr), hide_index=True, width="stretch")
        if show_info:
            st.caption(tr("Yahoo Finance (yfinance), ostatnia dostępna świeca minutowa sesji regularnej. "
                       "Dane mogą być opóźnione. Po zamknięciu rynku widoczne jest ostatnie notowanie."))
    if show_info:
        st.caption(tr(f'Yahoo Finance · pobrano {display_time(fetched, "%H:%M:%S")} · ceny mogą być opóźnione'))
    render_data_notes()
    old = [symbol for symbol, q in quotes.items()
           if (datetime.now(timezone.utc) - q["timestamp"]).total_seconds() > 1200]
    if old and show_info:
        st.warning(tr("Notowania starsze niż 20 minut: " + ", ".join(old)
                   + ". Rynek może być zamknięty lub dane dostawcy opóźnione."))


dashboard()
