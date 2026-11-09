"""Rotating UTC logs for access events and application errors."""
import json
import logging
from functools import lru_cache
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
from threading import RLock
import time

_LOCK = RLock()
_DEFAULT_LOG_DIR = str(Path(__file__).resolve().parent.parent / "logs")


def configure_logs():
    return _configure_logs(os.environ.get("LOG_DIR", _DEFAULT_LOG_DIR))


@lru_cache(maxsize=8)
def _configure_logs(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter("%(asctime)sZ %(levelname)s %(message)s", "%Y-%m-%dT%H:%M:%S")
    formatter.converter = time.gmtime
    with _LOCK:
        for name, filename, level in (("portfolio.access", "access.log", logging.INFO),
                                       ("portfolio.error", "error.log", logging.WARNING)):
            logger = logging.getLogger(name)
            target = str((directory / filename).resolve())
            if not any(getattr(h, "baseFilename", None) == target for h in logger.handlers):
                handler = RotatingFileHandler(target, maxBytes=5 * 1024 * 1024,
                                               backupCount=5, encoding="utf-8")
                handler.setFormatter(formatter)
                handler.setLevel(level)
                logger.addHandler(handler)
            logger.setLevel(level)
            logger.propagate = False
    return logging.getLogger("portfolio.access"), logging.getLogger("portfolio.error")


class AccessLogMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            return await self.app(scope, receive, send)
        access, errors = configure_logs()
        started, status = time.perf_counter(), 500
        async def capture(message):
            nonlocal status
            if message["type"] in ("http.response.start", "websocket.http.response.start"):
                status = message["status"]
            elif message["type"] == "websocket.accept":
                status = 101
            elif message["type"] == "websocket.close" and status == 500:
                status = 403
            await send(message)
        try:
            await self.app(scope, receive, capture)
        except Exception:
            errors.exception("Unhandled %s request error", scope["type"])
            raise
        finally:
            access.info(json.dumps({"event": "request", "type": scope["type"],
                "client": (scope.get("client") or ["unknown"])[0],
                "method": scope.get("method", "WS"), "path": scope.get("path", ""),
                "status": status, "duration_ms": round((time.perf_counter() - started) * 1000, 2)},
                ensure_ascii=False))


def log_script_error(exc):
    _, logger = configure_logs()
    logger.error("Streamlit script error", exc_info=(type(exc), exc, exc.__traceback__))
    return False
