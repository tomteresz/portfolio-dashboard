"""HTTP endpoints issue and revoke HttpOnly cookies outside the WebSocket UI."""
from threading import Lock
import time
from urllib.parse import parse_qs, urlsplit

from starlette.concurrency import run_in_threadpool
from starlette.responses import PlainTextResponse, RedirectResponse
from starlette.routing import Route

from portfolio_app.app_logging import configure_logs
from portfolio_app.auth import verify_credentials
from portfolio_app.auth_sessions import COOKIE_NAME, SESSION_SECONDS, create_session, revoke_session
from portfolio_app.i18n import LANGUAGE_COOKIE_NAME, LANGUAGE_SECONDS, resolve_language

_attempts = {}
_lock = Lock()


def _request_language(request, fields=None):
    return resolve_language((fields or {}).get("language"), request.query_params.get("lang"),
                            request.cookies.get(LANGUAGE_COOKIE_NAME))


def _redirect(request, language, error=None):
    url = f"/?lang={language}" + (f"&login_error={error}" if error else "")
    response = RedirectResponse(url, status_code=303)
    response.set_cookie(LANGUAGE_COOKIE_NAME, language, max_age=LANGUAGE_SECONDS,
                        httponly=True, secure=request.url.scheme == "https", samesite="lax", path="/")
    return response


async def _fields(request):
    origin = request.headers.get("origin")
    try:
        if (origin and urlsplit(origin).netloc != request.headers.get("host")) or request.headers.get("sec-fetch-site") == "cross-site":
            return None
        size = int(request.headers.get("content-length", "0"))
    except ValueError:
        return None
    if not 0 <= size <= 4096:
        return None
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > 4096:
            return None
        body.extend(chunk)
    try:
        fields = parse_qs(body.decode("utf-8", errors="replace"), max_num_fields=10)
    except ValueError:
        return None
    return {k: v[0] for k, v in fields.items()}


def _authenticate(username, password, previous_token):
    """Keep password hashing and SQLite I/O off the ASGI event loop."""
    if not verify_credentials(username, password):
        return None
    token = create_session()
    revoke_session(previous_token)
    return token


async def login(request):
    if request.method == "GET":
        return _redirect(request, _request_language(request))
    fields = await _fields(request)
    if fields is None:
        return PlainTextResponse("Forbidden", status_code=403)
    lang = _request_language(request, fields)
    client = request.client.host if request.client else "unknown"
    with _lock:
        now = time.monotonic()
        for key in list(_attempts):
            if _attempts[key][1] < now - 60:
                del _attempts[key]
        count, last = _attempts.get(client, (0, now))
        if count >= 5 and now < last + 60:
            return _redirect(request, lang, "blocked")
        # Reserve the attempt before verification: concurrent requests must
        # not all reuse the same count while a password hash is running.
        _attempts[client] = (count + 1, now)
    access, errors = configure_logs()
    try:
        token = await run_in_threadpool(_authenticate,
                                       fields.get("portfolio_username", ""),
                                       fields.get("portfolio_password", fields.get("password", "")),
                                       request.cookies.get(COOKIE_NAME))
        if token:
            response = _redirect(request, lang)
            response.set_cookie(COOKIE_NAME, token, max_age=SESSION_SECONDS, httponly=True,
                                secure=request.url.scheme == "https", samesite="lax", path="/")
            with _lock:
                _attempts.pop(client, None)
            access.info("event=login_success user=admin")
            return response
    except Exception:
        errors.exception("HTTP login failed")
        return PlainTextResponse("Sign-in unavailable. Please try again.", status_code=503)
    access.info("event=login_failure")
    return _redirect(request, lang, "invalid")


async def logout(request):
    fields = await _fields(request)
    if fields is None:
        return PlainTextResponse("Forbidden", status_code=403)
    await run_in_threadpool(revoke_session, request.cookies.get(COOKIE_NAME))
    response = _redirect(request, _request_language(request, fields))
    response.delete_cookie(COOKIE_NAME, path="/", httponly=True, samesite="lax")
    configure_logs()[0].info("event=logout user=admin")
    return response


ROUTES = [Route("/auth/login", login, methods=["GET", "POST"]), Route("/auth/logout", logout, methods=["POST"])]
