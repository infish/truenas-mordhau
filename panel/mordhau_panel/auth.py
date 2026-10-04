"""Signed session cookies for the panel login page."""

import hashlib
import hmac
import time

COOKIE_NAME = "panel_session"
SESSION_SECONDS = 30 * 24 * 3600


class SessionSigner:
    """Tokens are "<expiry>.<hmac>". The key derives from the panel password,
    so sessions survive restarts and a password change logs everyone out."""

    def __init__(self, password: str):
        self._key = hashlib.sha256(b"mordhau-panel-session:" + password.encode()).digest()

    def _sign(self, expiry: str) -> str:
        return hmac.new(self._key, expiry.encode(), hashlib.sha256).hexdigest()

    def issue(self, now: float | None = None) -> str:
        expiry = str(int((now if now is not None else time.time()) + SESSION_SECONDS))
        return f"{expiry}.{self._sign(expiry)}"

    def valid(self, token: str | None, now: float | None = None) -> bool:
        if not token:
            return False
        expiry, _, signature = token.partition(".")
        if not expiry.isdigit() or not hmac.compare_digest(signature, self._sign(expiry)):
            return False
        return int(expiry) > (now if now is not None else time.time())
