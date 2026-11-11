"""Offline smoke checks for the header and portfolio rendering."""
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import streamlit as st


class DashboardTests(unittest.TestCase):
    def setUp(self):
        source = (Path(__file__).resolve().parents[1] / 'portfolio_app/dashboard.py').read_text(encoding='utf-8')
        self.source = source
        now = datetime.now(timezone.utc)
        self.records = [dict(portfolio=p, symbol=s, name=s + ' Company', shares=2.0, average_price=80.0)
                        for p, s in [('Erste-DM', 'MSFT'), ('XTB', 'MSFT'), ('XTB', 'AAPL')]]
        quotes = {s: dict(price=100, previous_close=99, timestamp=now, fetched_at=now)
                  for s in ('MSFT', 'AAPL')}
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        # Keep AppTest scratch files in the writable workspace on Windows.
        scratch = Path(__file__).resolve().parents[1] / '.tmp'
        scratch.mkdir(exist_ok=True)
        self.stack.enter_context(patch.object(tempfile, 'tempdir', str(scratch)))
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', suffix='.py',
                                         dir=scratch, delete=False) as script:
            script.write(self.source)
            self.script_path = Path(script.name)
        self.addCleanup(self.script_path.unlink)
        for target, value in {
            'portfolio_app.auth.require_login': None,
            'portfolio_app.auth.logout_button': None,
            'portfolio_app.auth.is_authenticated': True,
            'portfolio_app.portfolio_store.load_positions': self.records,
            'portfolio_app.portfolio_names.load_portfolio_names': {'Erste-DM': 'Erste-DM', 'XTB': 'XTB'},
            'portfolio_app.market_data.fetch_quotes': (quotes, {}),
            'portfolio_app.market_data.fetch_usd_pln': (None, 'Unavailable'),
            'portfolio_app.company_news.fetch_news_batch': {s: ([], None, now) for s in quotes},
            'portfolio_app.investing_data.fetch_benchmarks': ({}, {}),
            'portfolio_app.market_data.fetch_vix': (None, 'Unavailable'),
            'portfolio_app.crude_oil.fetch_crude_oil': (None, 'Unavailable'),
            'portfolio_app.market_context.fetch_market_context': {},
            'portfolio_app.market_sentiment.fetch_sentiment': (None, 'Unavailable'),
            'portfolio_app.market_overview.fetch_sectors': {},
            'portfolio_app.market_overview.fetch_macro_calendar': {'events': [], 'failures': []},
        }.items():
            self.stack.enter_context(patch(target, return_value=value))
        st.cache_data.clear()
        self.addCleanup(st.cache_data.clear)

    def render(self, language='pl'):
        from streamlit.testing.v1 import AppTest

        app = AppTest.from_file(str(self.script_path), default_timeout=20)
        app.query_params['lang'] = language
        app.run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        return app

    def test_header_and_holdings_in_both_languages(self):
        for language in ('pl', 'en'):
            with self.subTest(language=language):
                app = self.render(language)
                strips = [m.value for m in app.markdown if 'class="quote-strip"' in m.value]
                self.assertEqual(len(strips), 1)
                self.assertEqual(strips[0].count('class="ticker-logo"'), 2)
                self.assertEqual(len(app.tabs), 2)
                self.assertNotIn('Logos provided by Parqet', str(app))

    def test_market_data_cache_survives_rerun(self):
        with patch('portfolio_app.market_data.fetch_vix', return_value=(None, 'Unavailable')) as fetch:
            app = self.render()
            app.run()
            self.assertFalse(app.exception, [e.message for e in app.exception])
            self.assertEqual(fetch.call_count, 1)

    def test_manual_refresh_reloads_parallel_market_data(self):
        with patch('portfolio_app.market_data.fetch_vix', return_value=(None, 'Unavailable')) as fetch:
            app = self.render('en')
            next(button for button in app.button if 'Refresh prices' in button.label).click().run()
            self.assertFalse(app.exception, [e.message for e in app.exception])
            self.assertEqual(fetch.call_count, 2)

    def test_empty_portfolios(self):
        with patch('portfolio_app.portfolio_store.load_positions', return_value=[]):
            app = self.render()
        self.assertFalse(any('class="quote-strip"' in m.value for m in app.markdown))

    def test_overall_returns_use_displayed_fx_rate(self):
        fx = {'price': 4.123456, 'timestamp': datetime.now(timezone.utc)}
        with patch('portfolio_app.market_data.fetch_usd_pln', return_value=(fx, None)):
            app = self.render('en')
        daily = [metric for metric in app.metric if metric.label == 'Daily change']
        returns = [metric for metric in app.metric if metric.label == 'Total return']
        self.assertEqual(daily[0].delta, '+6.00 USD  \n+24.74 PLN')
        self.assertEqual(returns[0].delta, '+120.00 USD  \n+494.82 PLN')
        self.assertTrue(all('PLN' not in metric.delta for metric in daily[1:] + returns[1:]))

    def test_missing_fx_preserves_usd_returns(self):
        app = self.render('en')
        daily = next(metric for metric in app.metric if metric.label == 'Daily change')
        total = next(metric for metric in app.metric if metric.label == 'Total return')
        self.assertEqual(daily.delta, '+6.00 USD  \n— PLN')
        self.assertEqual(total.delta, '+120.00 USD  \n— PLN')

    def test_negative_returns_keep_sign_in_both_currencies(self):
        now = datetime.now(timezone.utc)
        quotes = {s: dict(price=70, previous_close=75, timestamp=now, fetched_at=now)
                  for s in ('MSFT', 'AAPL')}
        fx = {'price': 4.0, 'timestamp': now}
        with patch('portfolio_app.market_data.fetch_usd_pln', return_value=(fx, None)), \
                patch('portfolio_app.market_data.fetch_quotes', return_value=(quotes, {})):
            app = self.render('en')
        daily = next(metric for metric in app.metric if metric.label == 'Daily change')
        total = next(metric for metric in app.metric if metric.label == 'Total return')
        self.assertEqual(daily.delta, '-30.00 USD  \n-120.00 PLN')
        self.assertEqual(total.delta, '-60.00 USD  \n-240.00 PLN')

    def test_unavailable_quotes(self):
        with patch('portfolio_app.market_data.fetch_quotes', return_value=({}, {'MSFT': 'offline', 'AAPL': 'offline'})):
            app = self.render()
        self.assertEqual(len(app.error), 1)
