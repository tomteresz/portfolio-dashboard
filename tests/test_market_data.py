"""Regression checks for pre-market quotes before regular-session bars exist."""
from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import Mock, patch

import pandas as pd

from portfolio_app import market_data as market


NOW = datetime(2026, 11, 9, 9, 5, tzinfo=timezone.utc)


def metadata(day=9):
    def at(hour, minute=0):
        return datetime(2026, 11, day, hour, minute, tzinfo=timezone.utc)
    return {
        "currency": "USD", "exchangeTimezoneName": "America/New_York",
        "currentTradingPeriod": {
            "pre": {"start": at(9), "end": at(14, 30)},
            "regular": {"start": at(14, 30), "end": at(21)},
            "post": {"start": at(21), "end": at(23)},
        },
    }


def bars(price=None, timestamp=NOW - timedelta(minutes=1)):
    index = pd.DatetimeIndex([] if price is None else [timestamp], tz="UTC")
    return pd.DataFrame({"Close": [] if price is None else [price]}, index=index)


class PreMarketTests(unittest.TestCase):
    def test_cold_fetch_accepts_quotes_arriving_during_network_requests(self):
        for symbol in ("INTC", "MSFT", "AMZN", "GOOGL"):
            with self.subTest(symbol=symbol):
                ticker = Mock()
                ticker.get_info.return_value = {
                    "preMarketPrice": 101,
                    "preMarketTime": (NOW + timedelta(minutes=1)).timestamp(),
                }
                ticker.history.return_value = pd.concat([
                    bars(96, NOW - timedelta(minutes=1)),
                    bars(102, NOW + timedelta(minutes=2)),
                ])
                with patch.object(market, "datetime", wraps=datetime) as clock, \
                        patch.object(market, "_previous_close", return_value=100):
                    clock.now.side_effect = [NOW, NOW + timedelta(minutes=1), NOW + timedelta(minutes=2),
                                            *[NOW + timedelta(minutes=3)] * 3]
                    quote = market._extended_quotes(symbol, ticker, metadata())["pre_market"]
                    next_quote = market._extended_quotes(symbol, ticker, metadata())["pre_market"]
                self.assertEqual(quote["price"], 102)
                self.assertAlmostEqual(quote["change_percent"], 2)
                self.assertEqual(quote, next_quote)

    def test_regular_open_during_fetch_hides_premarket(self):
        opening = metadata()["currentTradingPeriod"]["regular"]["start"]
        ticker = Mock()
        ticker.get_info.return_value = {
            "preMarketPrice": 101,
            "preMarketTime": (opening - timedelta(seconds=30)).timestamp(),
        }
        with patch.object(market, "datetime", wraps=datetime) as clock:
            clock.now.side_effect = [opening - timedelta(seconds=10), opening]
            result = market._extended_quotes("MSFT", ticker, metadata())
        self.assertIsNone(result["pre_market"])
        ticker.history.assert_not_called()

    def test_cold_fetch_still_rejects_genuinely_future_bars(self):
        ticker = Mock()
        ticker.get_info.return_value = {}
        ticker.history.return_value = pd.concat([
            bars(101, NOW + timedelta(minutes=1)),
            bars(999, NOW + timedelta(minutes=3)),
        ])
        with patch.object(market, "datetime", wraps=datetime) as clock, \
                patch.object(market, "_previous_close", return_value=100):
            clock.now.side_effect = [NOW, NOW + timedelta(minutes=1), NOW + timedelta(minutes=2)]
            quote = market._extended_quotes("MSFT", ticker, metadata())["pre_market"]
        self.assertEqual(quote["price"], 101)

    def test_empty_regular_day_still_fetches_premarket(self):
        ticker = Mock()
        ticker.history.side_effect = [bars(), bars(100, NOW - timedelta(days=3))]
        ticker.get_history_metadata.return_value = metadata()
        extended = {"pre_market": {"price": 102}, "after_hours": None}
        with patch("yfinance.Ticker", return_value=ticker), \
                patch.object(market, "_previous_close", return_value=99), \
                patch.object(market, "_extended_quotes", return_value=extended) as fetch:
            quote = market.fetch_quote("AAPL")
        self.assertEqual(quote["price"], 100)
        self.assertEqual(quote["pre_market"]["price"], 102)
        self.assertEqual(ticker.history.call_args.kwargs["period"], "5d")
        fetch.assert_called_once()

    def test_refresh_previous_session_schedule_and_use_minute_bars(self):
        ticker = Mock()
        ticker.history.return_value = bars(102)
        ticker.get_history_metadata.return_value = metadata()
        ticker.get_info.return_value = {}
        schedule = metadata(6)
        with patch.object(market, "_previous_close", return_value=100):
            result = market._extended_quotes("AAPL", ticker, schedule, NOW)
        self.assertEqual(result["pre_market"]["price"], 102)
        self.assertAlmostEqual(result["pre_market"]["change_percent"], 2)
        self.assertEqual(result["pre_market"]["source"], "yahoo_1m")
        self.assertIsNotNone(market.extended_value({
            "regular_session": schedule["currentTradingPeriod"]["regular"],
            **result,
        }, "pre_market", NOW))
        ticker.history.assert_called_once()

    def test_direct_quote_is_preferred_when_newer_than_bars(self):
        ticker = Mock()
        ticker.history.return_value = bars(101, NOW - timedelta(minutes=2))
        ticker.get_info.return_value = {
            "preMarketPrice": 102, "preMarketChangePercent": 2,
            "preMarketTime": (NOW - timedelta(minutes=1)).timestamp(),
        }
        with patch.object(market, "_previous_close", return_value=100):
            result = market._extended_quotes("AAPL", ticker, metadata(), NOW)
        self.assertEqual(result["pre_market"]["source"], "yahoo_quote")
        self.assertAlmostEqual(result["pre_market"]["change_percent"], 2)

    def test_intc_newer_bar_replaces_old_direct_quote(self):
        # Synthetic prices reproduce the reported -3.7% versus -1.45% gap.
        ticker = Mock()
        ticker.history.return_value = bars(98.55)
        ticker.get_info.return_value = {
            "preMarketPrice": 96.3, "preMarketChangePercent": -3.7,
            "preMarketTime": (NOW - timedelta(minutes=4)).timestamp(),
        }
        with patch.object(market, "_previous_close", return_value=100):
            quote = market._extended_quotes("INTC", ticker, metadata(), NOW)["pre_market"]
        self.assertEqual(quote["price"], 98.55)
        self.assertAlmostEqual(quote["change_percent"], -1.45)
        self.assertEqual(quote["source"], "yahoo_1m")

    def test_percentage_is_calculated_from_displayed_price_and_close(self):
        ticker = Mock()
        ticker.history.return_value = bars()
        ticker.get_info.return_value = {
            "preMarketPrice": 98.55, "preMarketChangePercent": -3.7,
            "preMarketTime": (NOW - timedelta(minutes=1)).timestamp(),
        }
        with patch.object(market, "_previous_close", return_value=100):
            quote = market._extended_quotes("INTC", ticker, metadata(), NOW)["pre_market"]
        self.assertAlmostEqual(quote["change_percent"], -1.45)

    def test_missing_close_does_not_show_unverified_provider_percentage(self):
        ticker = Mock()
        ticker.history.return_value = bars()
        ticker.get_info.return_value = {
            "preMarketPrice": 98.55, "preMarketChangePercent": -3.7,
            "preMarketTime": (NOW - timedelta(minutes=1)).timestamp(),
        }
        with patch.object(market, "_previous_close", side_effect=ValueError("No close")):
            quote = market._extended_quotes("INTC", ticker, metadata(), NOW)["pre_market"]
        self.assertEqual(quote["price"], 98.55)
        self.assertIsNone(quote["change_percent"])

    def test_old_and_future_bars_stay_hidden(self):
        ticker = Mock()
        ticker.get_info.return_value = {}
        ticker.history.return_value = pd.concat([
            bars(101, NOW - timedelta(days=3)), bars(103, NOW + timedelta(minutes=1)),
        ])
        result = market._extended_quotes("AAPL", ticker, metadata(), NOW)
        self.assertIsNone(result["pre_market"])

    def test_weekend_does_not_reuse_friday_session(self):
        ticker = Mock()
        ticker.history.return_value = bars(101, NOW - timedelta(days=3))
        ticker.get_history_metadata.return_value = metadata(6)
        result = market._extended_quotes("AAPL", ticker, metadata(6), NOW - timedelta(days=1))
        self.assertIsNone(result["pre_market"])
        self.assertIsNone(result["after_hours"])

    def test_cached_premarket_hidden_at_regular_open(self):
        quote = {
            "regular_session": metadata()["currentTradingPeriod"]["regular"],
            "pre_market": {"price": 102, "timestamp": NOW},
        }
        opening = datetime(2026, 11, 9, 14, 30, tzinfo=timezone.utc)
        self.assertIsNone(market.extended_value(quote, "pre_market", opening))


if __name__ == "__main__":
    unittest.main()
