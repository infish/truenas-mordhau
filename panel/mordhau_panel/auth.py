"""Panel login: password storage, setup state and signed session cookies."""

import hashlib
import hmac
import os
import secrets
import time
from pathlib import Path

from .settings import read_env_file

COOKIE_NAME = "panel_session"
SESSION_SECONDS = 30 * 24 * 3600
SCRYPT_PARAMS = {"n": 2**14, "r": 8, "p": 1, "dklen": 32}
# No 0/O/1/I so the code is easy to copy from a log.
SETUP_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


class SessionSigner:
    """Tokens are "<expiry>.<hmac>"; changing the key logs everyone out."""

    def __init__(self, key: bytes):
        self._key = key

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


def session_key_from_password(password: str) -> bytes:
    return hashlib.sha256(b"mordhau-panel-session:" + password.encode()).digest()


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, **SCRYPT_PARAMS)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    scheme, _, rest = stored.partition("$")
    salt_hex, _, digest_hex = rest.partition("$")
    if scheme != "scrypt" or not salt_hex or not digest_hex:
        return False
    try:
        expected = hash_password(password, bytes.fromhex(salt_hex))
    except ValueError:
        return False
    return hmac.compare_digest(expected, stored)


def new_setup_code() -> str:
    code = "".join(secrets.choice(SETUP_CODE_ALPHABET) for _ in range(8))
    return f"{code[:4]}-{code[4:]}"


def normalize_code(code: str) -> str:
    return "".join(ch for ch in code.upper() if ch.isalnum())


def _write_private(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(text)
    os.replace(tmp, path)


class PanelAuth:
    """The panel password comes from PANEL_PASSWORD, or else from the hash the
    setup screen stores in panel-auth.env. With neither, setup is required."""

    def __init__(self, panel_dir: Path, env_password: str | None):
        self.path = panel_dir / "panel-auth.env"
        self.env_password = env_password or None
        self._load()

    def _load(self) -> None:
        stored = read_env_file(self.path) or {}
        self._hash = stored.get("PASSWORD_HASH")
        key_hex = stored.get("SESSION_KEY", "")
        if self.env_password:
            self.signer = SessionSigner(session_key_from_password(self.env_password))
        elif self._hash and key_hex:
            self.signer = SessionSigner(bytes.fromhex(key_hex))
        else:
            self.signer = SessionSigner(secrets.token_bytes(32))

    @property
    def managed_by(self) -> str | None:
        if self.env_password:
            return "env"
        return "panel" if self._hash else None

    @property
    def needs_setup(self) -> bool:
        return self.managed_by is None

    def check(self, password: str) -> bool:
        if self.env_password:
            return secrets.compare_digest(password.encode(), self.env_password.encode())
        return bool(self._hash) and verify_password(password, self._hash)

    def set_password(self, password: str) -> None:
        """Stores a new hash and session key, which logs out other sessions."""
        if self.env_password:
            raise ValueError("The panel password is set by PANEL_PASSWORD in the app config")
        _write_private(self.path, f"PASSWORD_HASH={hash_password(password)}\nSESSION_KEY={secrets.token_hex(32)}\n")
        self._load()


def ensure_rcon_password(panel_dir: Path, env_password: str | None) -> str:
    """Uses RCON_PASSWORD when set; otherwise generates one and shares it with the
    server container through rcon.env, so nobody has to type it anywhere."""
    if env_password:
        return env_password
    path = panel_dir / "rcon.env"
    stored = (read_env_file(path) or {}).get("RCON_PASSWORD")
    if stored:
        return stored
    password = secrets.token_urlsafe(24)
    _write_private(path, f"RCON_PASSWORD={password}\n")
    return password
