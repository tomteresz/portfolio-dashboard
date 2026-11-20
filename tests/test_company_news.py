"""Regression coverage for Yahoo article artwork and duplicate feeds."""
from datetime import datetime, timezone
import unittest
from unittest.mock import patch

from portfolio_app.company_news import normalize_news, select_headlines


class CompanyNewsTests(unittest.TestCase):
    def test_news_prefers_a_preview_and_ignores_invalid_image_urls(self):
        now = datetime(2026, 11, 20, 15, tzinfo=timezone.utc)
        image = "https://s.yimg.com/news/preview.jpg"
        article = {"title": "The company announces new results today", "canonicalUrl": {"url": "https://example.com/story"},
                   "pubDate": now.isoformat(), "thumbnail": {"originalUrl": "https://example.com/large.jpg", "resolutions": [
                       {"width": 1600, "url": "https://example.com/large.jpg"},
                       {"width": 420, "url": "https://user@example.com/rejected.jpg"},
                       {"width": 170, "url": image},
                   ]}}
        with patch("portfolio_app.company_news.is_english", return_value=True):
            preview, = normalize_news([{"content": article}], "MSFT", now)
            missing, = normalize_news([{"content": {**article, "thumbnail": {"originalUrl": "javascript:bad"}}}], "AAPL", now)
        self.assertEqual(preview["thumbnail"], image)
        self.assertIsNone(missing["thumbnail"])
        merged, = select_headlines([[missing], [preview]])
        self.assertEqual(merged["symbols"], ["AAPL", "MSFT"])
        self.assertEqual(merged["thumbnail"], image)

    def test_news_uses_outer_thumbnail_when_content_thumbnail_is_invalid(self):
        now = datetime(2026, 11, 20, 15, tzinfo=timezone.utc)
        image = "https://s.yimg.com/news/fallback.jpg"
        item = {"thumbnail": image, "content": {
            "title": "The company announces new results today", "canonicalUrl": "https://example.com/story",
            "pubDate": now.isoformat(), "thumbnail": {"originalUrl": "javascript:bad"},
        }}
        with patch("portfolio_app.company_news.is_english", return_value=True):
            article, = normalize_news([item], "MSFT", now)
        self.assertEqual(article["thumbnail"], image)
