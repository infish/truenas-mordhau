"""Server settings edited in the panel, stored in /data/panel/server.env.

Each key there overrides the matching app environment variable when the server
starts; keys left out keep the app value. Passwords are write-only: the panel
reports whether one is set but never sends it back to the browser.
"""

import os
from pathlib import Path

from .settings import read_env_file

MAX_NAME = 64
MAX_PASSWORD = 64
MAX_PLAYERS_LIMIT = 100


class ServerSettingsError(ValueError):
    pass


def read_raw_env(path: Path) -> dict[str, str] | None:
    """Like read_env_file but keeps surrounding spaces, which may be part of a password."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    values = {}
    for line in text.splitlines():
        key, sep, value = line.partition("=")
        if sep:
            values[key] = value
    return values


def _single_line(value: str, field: str, max_length: int, allow_empty: bool) -> str:
    if not isinstance(value, str):
        raise ServerSettingsError(f"{field} must be text")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise ServerSettingsError(f"{field} cannot contain line breaks or control characters")
    if len(value) > max_length:
        raise ServerSettingsError(f"{field} is limited to {max_length} characters")
    if not allow_empty and not value.strip():
        raise ServerSettingsError(f"{field} is required")
    return value


def validate_changes(changes: dict) -> dict[str, str]:
    """Maps API field names to server.env keys, validating each provided value."""
    result = {}
    if changes.get("server_name") is not None:
        result["SERVER_NAME"] = _single_line(changes["server_name"].strip(), "Server name", MAX_NAME, False)
    if changes.get("max_players") is not None:
        players = changes["max_players"]
        if isinstance(players, bool) or not isinstance(players, int) or not 1 <= players <= MAX_PLAYERS_LIMIT:
            raise ServerSettingsError(f"Max players must be from 1 to {MAX_PLAYERS_LIMIT}")
        result["MAX_PLAYERS"] = str(players)
    if changes.get("advertise") is not None:
        result["ADVERTISE_SERVER"] = "true" if changes["advertise"] else "false"
    for field, key, label in (("server_password", "SERVER_PASSWORD", "Join password"),
                              ("admin_password", "ADMIN_PASSWORD", "Admin password")):
        if changes.get(f"clear_{field}"):
            result[key] = ""
        elif changes.get(field):
            result[key] = _single_line(changes[field], label, MAX_PASSWORD, False)
    return result


class ServerSettingsStore:
    def __init__(self, panel_dir: Path):
        self.panel_dir = panel_dir
        self.path = panel_dir / "server.env"
        self.effective_path = panel_dir / "effective.env"

    @property
    def exists(self) -> bool:
        return self.path.exists()

    def update(self, changes: dict) -> None:
        values = validate_changes(changes)
        merged = {**(read_raw_env(self.path) or {}), **values}
        self.panel_dir.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write("".join(f"{key}={value}\n" for key, value in merged.items()))
        os.replace(tmp, self.path)

    def view(self) -> dict:
        saved = read_raw_env(self.path) or {}
        effective = read_env_file(self.effective_path) or {}

        def password_set(key: str) -> bool | None:
            if key in saved:
                return bool(saved[key])
            flag = effective.get(f"HAS_{key}")
            return None if flag is None else flag == "true"

        max_players = saved.get("MAX_PLAYERS") or effective.get("MAX_PLAYERS")
        advertise = saved.get("ADVERTISE_SERVER") or effective.get("ADVERTISE_SERVER")
        return {
            "server_name": saved.get("SERVER_NAME") or effective.get("SERVER_NAME"),
            "max_players": int(max_players) if max_players and max_players.isdigit() else None,
            "advertise": None if advertise is None else advertise == "true",
            "server_password_set": password_set("SERVER_PASSWORD"),
            "admin_password_set": password_set("ADMIN_PASSWORD"),
            "saved_in_panel": sorted(saved),
        }
