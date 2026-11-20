"""Persist one post-close Finviz market breadth snapshot per US session."""
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3

from portfolio_app.market_context import EXCHANGE_ZONE
from portfolio_app.market_data import _instant
from portfolio_app.portfolio_store import PORTFOLIO_PATH

BREADTH_HISTORY_DAYS = 14
_AFTER_CLOSE = timedelta(minutes=15)


def _after_close(fetched_at, regular_session):
    try:
        start = _instant(regular_session["start"])
        end = _instant(regular_session["end"])
    except (KeyError, TypeError, AttributeError, ValueError, OverflowError, OSError):
        return False
    return (start < end and fetched_at >= end + _AFTER_CLOSE
            and fetched_at.astimezone(EXCHANGE_ZONE).date() == end.astimezone(EXCHANGE_ZONE).date())


def load_breadth_history(breadth, regular_session, *, now=None, path=None):
    """Update with the latest eligible sample and read the rolling calendar window."""
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(EXCHANGE_ZONE).date()
    first_day = today - timedelta(days=BREADTH_HISTORY_DAYS - 1)
    path = Path(path) if path is not None else PORTFOLIO_PATH.with_name("market_breadth.sqlite3")

    fetched_at = breadth["fetched_at"] if breadth else None
    save = (fetched_at is not None and fetched_at <= now
            and fetched_at.astimezone(EXCHANGE_ZONE).date() == today
            and _after_close(fetched_at, regular_session))
    if not save and not path.exists():
        return []

    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path, timeout=2)) as db, db:
        db.execute("""CREATE TABLE IF NOT EXISTS breadth (
            day TEXT PRIMARY KEY, fetched_at REAL NOT NULL,
            advancing INTEGER NOT NULL, declining INTEGER NOT NULL
        )""")
        if save:
            db.execute("""INSERT INTO breadth (day, fetched_at, advancing, declining)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(day) DO UPDATE SET fetched_at = excluded.fetched_at,
                    advancing = excluded.advancing, declining = excluded.declining
                WHERE excluded.fetched_at > breadth.fetched_at
            """, (today.isoformat(), fetched_at.timestamp(), breadth["advancing"], breadth["declining"]))
        rows = db.execute("""SELECT day, advancing, declining FROM breadth
            WHERE day BETWEEN ? AND ? ORDER BY day
        """, (first_day.isoformat(), today.isoformat())).fetchall()
    return [{"day": day, "advancing": up, "declining": down, "net": up - down}
            for day, up, down in rows]
