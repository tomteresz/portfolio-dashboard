"""Main entry point: python -m streamlit run app.py."""
from pathlib import Path
import asyncio
from contextlib import asynccontextmanager, suppress
import webbrowser

import streamlit as st
from streamlit import config
from starlette.middleware import Middleware

from portfolio_app.app_logging import AccessLogMiddleware, configure_logs, log_script_error
from portfolio_app.auth_routes import ROUTES
from portfolio_app.windows_asyncio import install_transport_cleanup

configure_logs()
install_transport_cleanup()


@asynccontextmanager
async def startup(_):
    browser_task = None
    if not config.get_option("server.headless"):
        # st.App's ASGI runner does not use the usual CLI browser-opening hook.
        async def open_browser():
            await asyncio.sleep(1)
            host = config.get_option("browser.serverAddress") or "localhost"
            if ":" in host and not host.startswith("["):
                host = f"[{host}]"
            port = config.get_option("server.port")
            path = config.get_option("server.baseUrlPath").strip("/")
            scheme = "https" if config.get_option("server.sslCertFile") else "http"
            url = f"{scheme}://{host}:{port}/" + (path + "/" if path else "")
            await asyncio.to_thread(webbrowser.open, url)
        browser_task = asyncio.create_task(open_browser())
    try:
        yield
    finally:
        if browser_task:
            browser_task.cancel()
            with suppress(asyncio.CancelledError):
                await browser_task


app = st.App(Path(__file__).with_name("portfolio_app") / "dashboard.py", routes=ROUTES,
             middleware=[Middleware(AccessLogMiddleware)], on_script_error=log_script_error,
             lifespan=startup)
