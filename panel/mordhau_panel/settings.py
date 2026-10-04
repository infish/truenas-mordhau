"""Map settings shared with the server container through files under /data/panel.

settings.env     written here; the server applies it on its next start
effective.env    written by the server: what it actually started with
restart-request  created here; the server's supervisor restarts the game
"""

import os
import re
from pathlib import Path

MAP_NAME_RE = re.compile(r"^[A-Za-z0-9_]+$")
MAX_ROTATION = 100


class SettingsError(ValueError):
    pass


def validate_map(name: str) -> str:
    if not isinstance(name, str) or not MAP_NAME_RE.match(name):
        raise SettingsError(f"Invalid map name: {name!r}")
    return name


def read_env_file(path: Path) -> dict[str, str] | None:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    values = {}
    for line in text.splitlines():
        key, sep, value = line.partition("=")
        if sep:
            values[key.strip()] = value.strip()
    return values


def _map_settings(values: dict[str, str] | None) -> dict | None:
    if values is None:
        return None
    rotation = [m for m in values.get("MAP_ROTATION", "").split(",") if m]
    result = {"default_map": values.get("DEFAULT_MAP") or None, "rotation": rotation}
    if "STARTED_AT" in values and values["STARTED_AT"].isdigit():
        result["started_at"] = int(values["STARTED_AT"])
    return result


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


class SettingsStore:
    def __init__(self, panel_dir: Path):
        self.panel_dir = panel_dir
        self.settings_path = panel_dir / "settings.env"
        self.effective_path = panel_dir / "effective.env"
        self.restart_path = panel_dir / "restart-request"

    def state(self) -> dict:
        return {
            "saved": _map_settings(read_env_file(self.settings_path)),
            "effective": _map_settings(read_env_file(self.effective_path)),
            "restart_pending": self.restart_path.exists(),
        }

    def save(self, default_map: str, rotation: list[str]) -> None:
        validate_map(default_map)
        if not rotation:
            raise SettingsError("Rotation needs at least one map")
        if len(rotation) > MAX_ROTATION:
            raise SettingsError(f"Rotation is limited to {MAX_ROTATION} maps")
        for name in rotation:
            validate_map(name)
        self.panel_dir.mkdir(parents=True, exist_ok=True)
        _atomic_write(self.settings_path, f"DEFAULT_MAP={default_map}\nMAP_ROTATION={','.join(rotation)}\n")

    def clear(self) -> None:
        self.settings_path.unlink(missing_ok=True)

    def request_restart(self) -> None:
        self.panel_dir.mkdir(parents=True, exist_ok=True)
        self.restart_path.touch()
