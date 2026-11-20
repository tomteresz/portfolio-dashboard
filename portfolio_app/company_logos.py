"""Company logos for the header quote strip, loaded by the browser."""

from html import escape
from urllib.parse import quote


def ticker_logo_url(symbol):
    return "https://assets.parqet.com/logos/symbol/" + quote(str(symbol).strip().upper(), safe="") + "?format=png&size=64"


def ticker_logo(symbol):
    """Build a logo request for any current or newly added portfolio symbol.

    Empty alternative text keeps failed images decorative: the adjacent ticker
    remains readable, while explicit dimensions prevent layout shifts.
    """
    return (f'<img class="ticker-logo" src="{escape(ticker_logo_url(symbol), quote=True)}" '
            'alt="" width="28" height="28" decoding="async" '
            'referrerpolicy="no-referrer">')
