"""Password verification and cookie-backed Streamlit authentication."""
import hmac
import json

import streamlit as st

from portfolio_app.app_logging import configure_logs
from portfolio_app.auth_sessions import COOKIE_NAME, is_demo_mode, valid_session
from portfolio_app.credentials import AUTH_PATH, password_hash
from portfolio_app.i18n import language, language_selector, tr


def verify_credentials(username, password):
    if is_demo_mode():
        return hmac.compare_digest(username.encode("utf-8"), b"admin")
    try:
        config = json.loads(AUTH_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return False
    derived = password_hash(password, bytes.fromhex(config["salt"]))
    password_ok = hmac.compare_digest(derived, config["password_hash"])
    username_ok = hmac.compare_digest(username.encode("utf-8"), config["username"].encode("utf-8"))
    return password_ok and username_ok


def is_authenticated():
    try:
        return valid_session(st.context.cookies.get(COOKIE_NAME))
    except Exception:
        configure_logs()[1].exception("Could not validate browser session")
        return False


def logout_button():
    st.html(f'<form action="/auth/logout" method="post"><input type="hidden" name="language" value="{language()}">'
            f'<button type="submit" style="padding:9px 18px;min-height:44px;border:1px solid #d7dce2;'
            f'border-radius:8px;background:#fff;color:#202833;cursor:pointer;font:inherit">{tr("Wyloguj")}</button></form>',
            width="content")


def login_dialog():
    @st.dialog(tr("Logowanie do MojePortfolio"), dismissible=False)
    def show():
        language_selector(key="login-language")
        if not is_demo_mode() and not AUTH_PATH.exists():
            st.info(tr("Brakuje pliku `data/auth.json`. Przywróć go z kopii zapasowej lub ustaw hasło administratora w terminalu w katalogu projektu. Następnie odśwież stronę."))
            st.code("python -m portfolio_app.credentials", language="shell")
            return
        st.caption(tr("Zaloguj się, aby przeglądać i modyfikować portfele."))
        error = st.query_params.get("login_error")
        if error:
            message = "Nieprawidłowy login." if is_demo_mode() else "Nieprawidłowy login lub hasło."
            st.error(tr("Zbyt wiele prób. Odczekaj minutę." if error == "blocked" else message))
        password_field = "" if is_demo_mode() else f'''
            <label for="portfolio-pass" style="display:block;margin:14px 0 6px">{tr("Hasło")}</label>
            <input id="portfolio-pass" name="portfolio_password" type="password" autocomplete="off"
              data-lpignore="true" data-1p-ignore="true" data-bwignore="true"
              autocapitalize="off" autocorrect="off" spellcheck="false" required maxlength="512"
              style="box-sizing:border-box;width:100%;font:inherit;font-size:16px;min-height:44px;padding:12px;border:1px solid #ccd2da;border-radius:8px">'''
        st.html(f'''<form action="/auth/login" method="post" autocomplete="off">
            <input type="hidden" name="language" value="{language()}">
            <label for="portfolio-user" style="display:block;margin:12px 0 6px">{tr("Login")}</label>
            <input id="portfolio-user" name="portfolio_username" value="admin" readonly
              autocomplete="off" data-lpignore="true" data-1p-ignore="true" maxlength="128"
              style="box-sizing:border-box;width:100%;font:inherit;font-size:16px;min-height:44px;padding:12px;border:1px solid #ccd2da;border-radius:8px">
            {password_field}
            <button type="submit" style="width:100%;min-height:44px;margin-top:20px;padding:12px;font:inherit;
              font-weight:600;border:0;border-radius:8px;background:#d98b12;color:#fff;cursor:pointer">{tr("Zaloguj się")}</button>
            </form>''')
    show()


def require_login():
    if not is_authenticated():
        login_dialog()
        st.stop()
