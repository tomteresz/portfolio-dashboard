"""WTI instrument validation, quote freshness, and daily comparison."""
from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import patch

from portfolio_app import crude_oil as oil


NOW = datetime(2026, 11, 9, 10, 0, tzinfo=timezone.utc)


def payload(**updates):
    meta = {"symbol": "CL=F", "currency": "USD", "instrumentType": "FUTURE",
            "regularMarketPrice": 90.29, "regularMarketTime": NOW.timestamp(),
            "previousClose": 90.83}
    meta.update(updates)
    return {"chart": {"error": None, "result": [{"meta": meta}]}}


class CrudeOilTests(unittest.TestCase):
    def test_reads_price_timestamp_and_calculates_change(self):
        quote = oil.parse_quote(payload(), NOW)
        self.assertEqual(quote["price"], 90.29)
        self.assertEqual(quote["timestamp"], NOW)
        self.assertAlmostEqual(quote["change"], -0.54)
        self.assertAlmostEqual(quote["change_percent"], -0.54 / 90.83 * 100)

    def test_rejects_other_instruments_and_invalid_quotes(self):
        for updates in ({"symbol": "BZ=F"}, {"currency": "EUR"}, {"instrumentType": "EQUITY"},
                        {"regularMarketPrice": float("nan")}, {"regularMarketPrice": True},
                        {"regularMarketTime": (NOW - timedelta(days=8)).timestamp()},
                        {"regularMarketTime": (NOW + timedelta(hours=1)).timestamp()}):
            with self.subTest(updates=updates), self.assertRaises(ValueError):
                oil.parse_quote(payload(**updates), NOW)

    def test_missing_or_zero_reference_preserves_price(self):
        for previous in (None, 0, float("nan")):
            with self.subTest(previous=previous):
                quote = oil.parse_quote(payload(previousClose=previous), NOW)
                self.assertEqual(quote["price"], 90.29)
                self.assertIsNone(quote["change_percent"])

    def test_uses_chart_reference_when_previous_close_is_missing(self):
        quote = oil.parse_quote(payload(previousClose=None, chartPreviousClose=90), NOW)
        self.assertAlmostEqual(quote["change"], 0.29)

    def test_network_failure_is_nonfatal(self):
        with patch.object(oil, "urlopen", side_effect=OSError("offline")):
            quote, error = oil.fetch_crude_oil()
        self.assertIsNone(quote)
        self.assertTrue(error)
