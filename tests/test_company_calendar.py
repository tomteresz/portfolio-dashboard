"""Declared dividend amounts, safe fallback, and calendar card rendering."""
import ast
from datetime import date, datetime, timezone
from html import escape
import json
import math
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

import pandas as pd

from portfolio_app import company_calendar as calendar


TODAY = date(2026, 11, 13)


def payload(amount="$0.98"):
    return {"status": {"rCode": 200}, "data": {"dividends": {"rows": [
        {"type": "Cash", "amount": amount, "currency": "USD",
         "exOrEffDate": "11/19/2026", "paymentDate": "12/10/2026"},
        {"type": "Cash", "amount": "$0.91", "currency": "USD",
         "exOrEffDate": "08/20/2026", "paymentDate": "09/10/2026"},
    ]}}}


class CompanyCalendarTests(unittest.TestCase):
    def test_reads_declared_amount_without_using_historical_payment(self):
        dividends = calendar.normalize_dividends(payload(), TODAY)
        self.assertEqual(len(dividends), 1)
        self.assertEqual(dividends[0]["amount"], 0.98)
        self.assertEqual(dividends[0]["currency"], "USD")

    def test_invalid_amount_preserves_dates(self):
        for amount in (None, "N/A", "NaN", "-1"):
            with self.subTest(amount=amount):
                dividend = calendar.normalize_dividends(payload(amount), TODAY)[0]
                self.assertIsNone(dividend["amount"])
                self.assertEqual(dividend["payment_date"], date(2026, 12, 10))

    def test_browser_transport_loads_amount_and_closes_response(self):
        with patch.object(calendar.requests, "Session") as factory, patch.object(calendar, "exchange_today", return_value=TODAY):
            session = factory.return_value.__enter__.return_value
            response = session.stream.return_value.__enter__.return_value
            response.iter_content.return_value = [json.dumps(payload()).encode()]
            self.assertEqual(calendar._nasdaq_dividends("MSFT")[0]["amount"], 0.98)
            factory.assert_called_once_with(impersonate="chrome")
            response.raise_for_status.assert_called_once()
            session.stream.return_value.__exit__.assert_called_once()

    def test_rejects_oversized_response(self):
        with patch.object(calendar.requests, "Session") as factory:
            response = factory.return_value.__enter__.return_value.stream.return_value.__enter__.return_value
            response.iter_content.return_value = [b"x" * 2_000_001]
            with self.assertRaisesRegex(ValueError, "too large"):
                calendar._nasdaq_dividends("MSFT")

    def test_network_failure_keeps_date_only_fallback(self):
        with patch("yfinance.Ticker") as factory, patch.object(calendar, "exchange_today", return_value=TODAY), patch.object(calendar, "_nasdaq_dividends", side_effect=OSError("offline")):
            ticker = factory.return_value
            ticker.get_calendar.return_value = {"Ex-Dividend Date": date(2026, 11, 19),
                                                "Dividend Date": date(2026, 12, 10),
                                                "Earnings Date": [date(2027, 1, 27)]}
            result = calendar.fetch_company_calendar("MSFT")
        self.assertIsNone(result["dividends"][0]["amount"])
        self.assertEqual(result["dividends"][0]["payment_date"], date(2026, 12, 10))
        self.assertIn("Nasdaq", result["issues"])

    def test_card_shows_amount_and_combined_holdings_total(self):
        # Run the actual renderer without starting the dashboard's data loaders.
        source = (Path(__file__).resolve().parents[1] / "portfolio_app/dashboard.py").read_text(encoding="utf-8")
        renderer = next(node for node in ast.parse(source).body if isinstance(node, ast.FunctionDef) and node.name == "render_calendar")
        st = MagicMock()
        events = {"MSFT": {"earnings": [], "dividends": calendar.normalize_dividends(payload(), TODAY),
                           "issues": [], "fetched_at": datetime.now(timezone.utc)}}
        namespace = dict(st=st, tr=lambda value: value, portfolio_label=lambda value: value,
                         load_calendars=lambda symbols: events, exchange_today=lambda: TODAY,
                         upcoming_earnings=calendar.upcoming_earnings, escape=escape,
                         date=date, math=math, display_time=str)
        exec(compile(ast.Module(body=[renderer], type_ignores=[]), "dashboard.py", "exec"), namespace)
        holdings = pd.DataFrame([{"Ticker": "MSFT", "Spółka": "Microsoft", "Portfel": portfolio, "Akcje": shares}
                                 for portfolio, shares in [("A", 100), ("B", 200)]])
        namespace["render_calendar"](holdings, "all", ["MSFT"])
        html = st.html.call_args.args[0]
        self.assertIn("0.98 USD", html)
        self.assertIn("294.00 USD", html)
        self.assertIn("10.12.2026", html)
        self.assertEqual(html.count('<article class="holding-card">'), 1)
