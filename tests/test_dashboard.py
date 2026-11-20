"""Offline smoke checks for the header and portfolio rendering."""
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
import json
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
            'portfolio_app.market_data.fetch_daily_history': [],
            'portfolio_app.crude_oil.fetch_crude_oil': (None, 'Unavailable'),
            'portfolio_app.market_context.fetch_market_context': {},
            'portfolio_app.breadth_history.load_breadth_history': [],
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

    def test_news_cards_show_thumbnails_and_fallback_logo(self):
        now = datetime.now(timezone.utc)
        photo_article = dict(title='Results & outlook', url='https://example.com/story?x=1&y=2',
                             published=now, source='Publisher', symbols=['MSFT'],
                             thumbnail='https://s.yimg.com/preview.jpg')
        fallback_article = dict(title='A second report', url='https://example.com/report', published=now,
                                source='Another publisher', symbols=['AAPL'])
        news = {'MSFT': ([photo_article], None, now), 'AAPL': ([fallback_article], None, now)}
        with patch('portfolio_app.company_news.fetch_news_batch', return_value=news):
            app = self.render('en')
        cards = next(item.proto.body for item in app.get('html') if 'class="news-grid"' in item.proto.body)
        self.assertEqual(cards.count('class="news-card"'), 2)
        self.assertEqual(cards.count('class="news-photo"'), 1)
        self.assertIn('background-image:url(&quot;https://s.yimg.com/preview.jpg&quot;)', cards)
        self.assertIn('/logos/symbol/AAPL?', cards)
        self.assertIn('Results &amp; outlook', cards)
        self.assertIn('href="https://example.com/story?x=1&amp;y=2"', cards)

    def test_daily_drivers_rank_aggregated_tickers_and_reconcile_pln(self):
        stamp = (datetime.now(timezone.utc) - timedelta(days=2)).replace(hour=20, minute=0)
        moves = {'MSFT': 5, 'AAPL': -4, 'CAT': 30, 'BA': 25, 'V': 8,
                 'IBM': -50, 'AMZN': -40, 'KO': -1, 'GS': 0}
        records = self.records + [dict(portfolio='XTB', symbol=symbol, name=symbol, shares=1, average_price=80)
                                  for symbol in moves if symbol not in ('MSFT', 'AAPL')]
        quotes = {symbol: dict(price=100 + move, previous_close=100, timestamp=stamp, fetched_at=stamp)
                  for symbol, move in moves.items()}
        news = {symbol: ([], None, stamp) for symbol in moves}
        fx = dict(price=4.125, previous_close=4.0, timestamp=stamp)
        fx_history = [{'day': (stamp - timedelta(days=1)).date().isoformat(), 'level': 4.0},
                      {'day': stamp.date().isoformat(), 'level': 4.1},
                      {'day': (stamp + timedelta(days=1)).date().isoformat(), 'level': 4.125}]
        with (
            patch('portfolio_app.portfolio_store.load_positions', return_value=records),
            patch('portfolio_app.market_data.fetch_quotes', return_value=(quotes, {})),
            patch('portfolio_app.company_news.fetch_news_batch', return_value=news),
            patch('portfolio_app.market_data.fetch_usd_pln', return_value=(fx, None)) as fetch_fx,
            patch('portfolio_app.market_data.fetch_daily_history',
                  side_effect=lambda symbol, **kwargs: fx_history if symbol == 'PLN=X' else []) as fetch_history,
        ):
            app = self.render('en')
            combined, erste, xtb = [item.proto.body for item in app.get('html')
                                    if 'class="daily-drivers"' in item.proto.body]
            self.assertIn('What moved the portfolio today?', combined)
            self.assertLess(combined.index('>CAT<'), combined.index('>BA<'))
            self.assertLess(combined.index('>BA<'), combined.index('>MSFT<'))
            self.assertLess(combined.index('>IBM<'), combined.index('>AMZN<'))
            self.assertLess(combined.index('>AMZN<'), combined.index('>AAPL<'))
            self.assertNotIn('>V<', combined)
            self.assertNotIn('>KO<', combined)
            self.assertNotIn('>GS<', combined)
            self.assertIn('+20.00</span></td><td>+82.50', combined)
            self.assertIn('USD/PLN impact <strong>+162.50 PLN', combined)
            self.assertIn('Daily change in PLN <strong>+96.50 PLN', combined)
            self.assertIn('+10.00</span></td><td>+41.25', erste)
            self.assertIn('+10.00</span></td><td>+41.25', xtb)
            self.assertEqual([call.args[0] for call in fetch_history.call_args_list].count('PLN=X'), 1)

            fetch_fx.return_value = ({**fx, 'timestamp': stamp + timedelta(days=1)}, None)
            next(button for button in app.button if 'Refresh prices' in button.label).click().run()
            self.assertFalse(app.exception, [e.message for e in app.exception])
            combined = next(item.proto.body for item in app.get('html') if 'class="daily-drivers"' in item.proto.body)
            self.assertIn('+20.00</span></td><td>+82.00', combined)
            self.assertIn('USD/PLN impact <strong>+130.00 PLN', combined)
            self.assertIn('Daily change in PLN <strong>+64.40 PLN', combined)
            self.assertIn('Converted using the historical USD/PLN close', combined)
            self.assertEqual([call.args[0] for call in fetch_history.call_args_list].count('PLN=X'), 2)

            fx_history.pop(1)
            next(button for button in app.button if 'Refresh prices' in button.label).click().run()
            self.assertFalse(app.exception, [e.message for e in app.exception])
            combined = next(item.proto.body for item in app.get('html') if 'class="daily-drivers"' in item.proto.body)
            self.assertIn('+20.00</span></td><td>—', combined)
            self.assertIn('USD/PLN impact <strong>—', combined)
            self.assertIn('Daily change in PLN <strong>—', combined)

    def test_manual_refresh_reloads_parallel_market_data(self):
        history = [{'day': '2026-11-18', 'level': 17.25}, {'day': '2026-11-19', 'level': 16.8}]
        with (
            patch('portfolio_app.market_data.fetch_vix', return_value=(None, 'Unavailable')) as fetch,
            patch('portfolio_app.market_data.fetch_daily_history', return_value=history) as fetch_history,
        ):
            app = self.render('en')
            caption = next(item for item in app.caption if item.value == 'VIX · last 14 days')
            container = next(block for block in app.get('flex_container') if caption in block.children.values())
            elements = list(container.children.values())
            self.assertEqual([item.type for item in elements],
                             ['metric', 'caption', 'vega_lite_chart'])
            self.assertEqual(elements[0].label, 'VIX · fear index')
            date_tooltip = json.loads(elements[-1].proto.spec)['encoding']['tooltip'][0]
            self.assertEqual(date_tooltip, {'field': 'day', 'type': 'temporal', 'title': 'Trading date',
                                            'timeUnit': 'utcyearmonthdate', 'format': '%d.%m.%Y'})
            for title, quote, container_type in (
                ('USD/PLN', 'USD/PLN', 'flex_container'),
                ('US 10Y', 'US 10Y', 'flex_container'),
                ('WTI', 'Crude Oil WTI (CL.F)', 'flex_container'),
                ('Nasdaq 100', 'US Tech 100', 'column'),
                ('S&P 500', 'US 500', 'column'),
            ):
                captions = [item for item in app.caption if item.value == f'{title} · last 14 days']
                self.assertEqual(len(captions), 1)
                caption, = captions
                container = next(block for block in app.get(container_type) if caption in block.children.values())
                *quote_elements, _, chart = container.children.values()
                self.assertEqual(chart.type, 'vega_lite_chart')
                self.assertEqual(json.loads(chart.proto.spec)['mark'], {'type': 'line', 'point': True})
                if container_type == 'column':
                    self.assertEqual(quote_elements[0].type, 'html')
                    self.assertIn(quote, quote_elements[0].proto.body)
                else:
                    self.assertEqual(quote_elements[0].label, quote)
            self.assertCountEqual([call.args[0] for call in fetch_history.call_args_list],
                                  ['PLN=X', '^VIX', '^TNX', 'CL=F', '^NDX', '^GSPC'])
            next(button for button in app.button if 'Refresh prices' in button.label).click().run()
            self.assertFalse(app.exception, [e.message for e in app.exception])
            self.assertEqual(fetch.call_count, 2)
            self.assertEqual(fetch_history.call_count, 12)

    def test_empty_portfolios(self):
        with patch('portfolio_app.portfolio_store.load_positions', return_value=[]):
            app = self.render()
        self.assertFalse(any('class="quote-strip"' in m.value for m in app.markdown))

    def test_breadth_chart_sits_below_metric_when_live_data_is_unavailable(self):
        history = [{'day': '2026-11-19', 'advancing': 2700, 'declining': 2300, 'net': 400}]
        with patch('portfolio_app.breadth_history.load_breadth_history', return_value=history):
            app = self.render('en')
        caption = next(item for item in app.caption if item.value == 'Advancing / declining · last 14 days')
        container = next(block for block in app.get('flex_container') if caption in block.children.values())
        metric, _, chart = container.children.values()
        self.assertEqual(metric.label, 'Market · advancing / declining')
        self.assertEqual(chart.type, 'vega_lite_chart')
        spec = json.loads(chart.proto.spec)
        self.assertEqual(spec['mark']['type'], 'line')
        self.assertEqual(spec['transform'][0]['fold'], ['Advancing issues', 'Declining issues'])
        self.assertEqual(spec['encoding']['tooltip'][0],
                         {'field': 'day', 'type': 'temporal', 'title': 'Trading date',
                          'timeUnit': 'utcyearmonthdate', 'format': '%d.%m.%Y'})

    def test_unavailable_quotes(self):
        with patch('portfolio_app.market_data.fetch_quotes', return_value=({}, {'MSFT': 'offline', 'AAPL': 'offline'})):
            app = self.render()
        self.assertEqual(len(app.error), 1)
