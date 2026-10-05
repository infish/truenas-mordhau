"""Map pictures imported with tools/import_map_icons.py.

They are Triternion's artwork, so they are not shipped with the panel: the
import tool reads them from a local game install and uploads them here, into
/data/panel/map-icons, together with manifest.json mapping level names (and
"*" for the fallback) to picture files.
"""

import json
import os
import re
from pathlib import Path

ICON_NAME_RE = re.compile(r"^[A-Za-z0-9_]{1,64}\.png$")
LEVEL_KEY_RE = re.compile(r"^([A-Za-z0-9_]{1,64}|\*)$")
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
MAX_ICON_BYTES = 1024 * 1024
MAX_ICONS = 200
MAX_MANIFEST_ENTRIES = 2000


class IconError(ValueError):
    pass


def _atomic_write(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


class MapIconStore:
    def __init__(self, directory: Path):
        self.directory = directory
        self.manifest_path = directory / "manifest.json"

    def icon_path(self, name: str) -> Path | None:
        if not ICON_NAME_RE.match(name):
            return None
        path = self.directory / name
        return path if path.is_file() else None

    def save_icon(self, name: str, data: bytes) -> None:
        if not ICON_NAME_RE.match(name):
            raise IconError("Picture names must look like Name_1.png")
        if not data.startswith(PNG_SIGNATURE):
            raise IconError("Pictures must be PNG files")
        if len(data) > MAX_ICON_BYTES:
            raise IconError("Picture is too large")
        self.directory.mkdir(parents=True, exist_ok=True)
        existing = {p.name for p in self.directory.glob("*.png")}
        if name not in existing and len(existing) >= MAX_ICONS:
            raise IconError(f"At most {MAX_ICONS} pictures")
        _atomic_write(self.directory / name, data)

    def save_manifest(self, manifest: dict) -> None:
        if not isinstance(manifest, dict) or len(manifest) > MAX_MANIFEST_ENTRIES:
            raise IconError("Manifest must map map names to picture files")
        for level, icon in manifest.items():
            if not isinstance(level, str) or not LEVEL_KEY_RE.match(level):
                raise IconError(f"Invalid map name in manifest: {level!r}")
            if not isinstance(icon, str) or self.icon_path(icon) is None:
                raise IconError(f"Manifest refers to a missing picture: {icon!r}")
        self.directory.mkdir(parents=True, exist_ok=True)
        _atomic_write(self.manifest_path, json.dumps(manifest, sort_keys=True).encode())

    def manifest(self) -> dict:
        """{"version": <changes when pictures change>, "icons": {level: file}}."""
        try:
            icons = json.loads(self.manifest_path.read_text(encoding="utf-8"))
            version = self.manifest_path.stat().st_mtime_ns
        except (FileNotFoundError, ValueError):
            return {"version": 0, "icons": {}}
        return {"version": version, "icons": icons if isinstance(icons, dict) else {}}

    def clear(self) -> None:
        if self.directory.is_dir():
            for path in self.directory.iterdir():
                if path.suffix in (".png", ".json", ".tmp"):
                    path.unlink()
