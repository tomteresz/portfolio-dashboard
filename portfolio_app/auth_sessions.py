"""Opaque browser sessions, valid for up to eight hours within one server run."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import time
from contextlib import closing

COOKIE_NAME = "portfolio_session"
SESSION_SECONDS = 8 * 60 * 60
AUTH_PATH = Path(__file__).resolve().parent.parent / "data" / "auth.json"
# Streamlit can unload application modules while HTTP routes still reference
# earlier imports. Keep the identity in process-local environment storage so
# both imports agree. An inherited identity belongs to a different PID and
# is never reused by a newly started server.
_SERVER_RUN_ID = os.environ.setdefault(
    f"MOJEPORTFOLIO_SERVER_RUN_{os.getpid()}", secrets.token_hex(32)
)


def _connection():
    path = Path(os.environ.get("SESSION_DB_PATH", str(Path(__file__).resolve().parent.parent / ".streamlit" / "sessions.sqlite3")))
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10)
    try:
        connection.execute("CREATE TABLE IF NOT EXISTS sessions (token_hash TEXT PRIMARY KEY, expires REAL, credential_hash TEXT)")
    except Exception:
        connection.close()
        raise
    return connection


def _fingerprint():
    config = json.loads(AUTH_PATH.read_text(encoding="utf-8"))
    identity = json.dumps([config["username"], config["password_hash"], _SERVER_RUN_ID])
    return hashlib.sha256(identity.encode()).hexdigest()


def create_session():
    token = secrets.token_urlsafe(32)
    fingerprint = _fingerprint()
    with closing(_connection()) as db, db:
        db.execute("DELETE FROM sessions WHERE expires <= ? OR credential_hash != ?",
                   (time.time(), fingerprint))
        db.execute("INSERT INTO sessions VALUES (?, ?, ?)",
                   (hashlib.sha256(token.encode()).hexdigest(), time.time() + SESSION_SECONDS, fingerprint))
    return token


def valid_session(token):
    if not isinstance(token, str) or not 20 <= len(token) <= 128:
        return False
    with closing(_connection()) as db, db:
        row = db.execute("SELECT expires, credential_hash FROM sessions WHERE token_hash = ?",
                         (hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
    return bool(row and row[0] > time.time() and row[1] == _fingerprint())


def revoke_session(token):
    if not token:
        return
    with closing(_connection()) as db, db:
        db.execute("DELETE FROM sessions WHERE token_hash = ?", (hashlib.sha256(token.encode()).hexdigest(),))
