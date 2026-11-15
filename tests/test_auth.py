"""Offline checks for demo sign-in and normal authentication isolation."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from portfolio_app import auth, auth_sessions


class AuthenticationTests(unittest.TestCase):
    def setUp(self):
        scratch = Path(__file__).resolve().parents[1] / ".tmp"
        scratch.mkdir(exist_ok=True)
        temporary = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.auth_path = self.directory / "auth.json"
        for target in (auth, auth_sessions):
            context = patch.object(target, "AUTH_PATH", self.auth_path)
            context.start()
            self.addCleanup(context.stop)
        environment = patch.dict(os.environ, {
            "PORTFOLIO_DEMO": "1",
            "SESSION_DB_PATH": str(self.directory / "sessions.sqlite3"),
        })
        environment.start()
        self.addCleanup(environment.stop)

    def configure_normal_credentials(self):
        salt = bytes.fromhex("12" * 16)
        digest = hashlib.scrypt(b"test-secret", salt=salt, n=16384, r=8, p=1, dklen=32)
        self.auth_path.write_text(json.dumps({
            "username": "admin", "salt": salt.hex(), "password_hash": digest.hex(),
        }), encoding="utf-8")

    def test_demo_accepts_only_admin_without_auth_file(self):
        self.assertTrue(auth.verify_credentials("admin", ""))
        for username in ("", "Admin", "other", "admin "):
            with self.subTest(username=username):
                self.assertFalse(auth.verify_credentials(username, ""))
        self.assertFalse(self.auth_path.exists())

    def test_demo_sessions_work_without_auth_file_and_can_be_revoked(self):
        token = auth_sessions.create_session()
        self.assertTrue(auth_sessions.valid_session(token))
        auth_sessions.revoke_session(token)
        self.assertFalse(auth_sessions.valid_session(token))

    def test_normal_mode_requires_password_and_rejects_demo_session(self):
        self.configure_normal_credentials()
        demo_token = auth_sessions.create_session()
        for flag in ("0", "", "true"):
            with self.subTest(flag=flag), patch.dict(os.environ, {"PORTFOLIO_DEMO": flag}):
                self.assertFalse(auth.verify_credentials("admin", ""))
                self.assertFalse(auth.verify_credentials("admin", "wrong"))
                self.assertFalse(auth.verify_credentials("other", "test-secret"))
                self.assertTrue(auth.verify_credentials("admin", "test-secret"))
                self.assertFalse(auth_sessions.valid_session(demo_token))
                normal_token = auth_sessions.create_session()
                self.assertTrue(auth_sessions.valid_session(normal_token))
            self.assertFalse(auth_sessions.valid_session(normal_token))

    def test_password_field_is_present_only_in_normal_mode(self):
        for flag in ("1", "0"):
            with self.subTest(flag=flag), patch.dict(os.environ, {"PORTFOLIO_DEMO": flag}), \
                    patch.object(auth.st, "dialog", side_effect=lambda *a, **k: lambda fn: fn), \
                    patch.object(auth.st, "caption"), patch.object(auth.st, "query_params", {}), \
                    patch.object(auth.st, "html") as html, \
                    patch.object(auth, "language_selector"), patch.object(auth, "language", return_value="en"), \
                    patch.object(auth, "tr", side_effect=lambda text: text):
                auth.login_dialog()
                form = html.call_args.args[0]
                self.assertIn('value="admin"', form)
                self.assertEqual('type="password"' in form, flag != "1")


if __name__ == "__main__":
    unittest.main()
