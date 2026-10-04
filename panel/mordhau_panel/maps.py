"""Discovers playable maps by reading .umap names from the server's .pak indexes."""

import io
import re
import struct
from pathlib import Path

PAK_MAGIC = struct.pack("<I", 0x5A6F12E1)
FOOTER_SEARCH_BYTES = 1024
MAX_INDEX_BYTES = 64 * 1024 * 1024

# Game modes are encoded as the map name prefix (FFA_Camp, TDM_Camp, ...).
MODE_LABELS = {
    "FFA": "Free-for-all",
    "TDM": "Team deathmatch",
    "SKM": "Skirmish",
    "FL": "Frontline",
    "INV": "Invasion",
    "HRD": "Horde",
    "BR": "Battle royale",
    "DU": "Duel",
    # Demon Invasion horde maps; their assets sit next to BP_HolyGun_DIH.
    "DIH": "Demon Invasion",
}
MODE_ORDER = list(MODE_LABELS)
# Tutorial/scenario levels are not meant to be hosted.
HIDDEN_PREFIXES = {"SC"}

MAP_NAME_RE = re.compile(r"^([A-Z]{2,3})_[A-Za-z0-9_]+$")
UMAP_RE = re.compile(rb"([A-Za-z0-9_]+)\.umap")


def _read_fstring(buf: io.BytesIO) -> str:
    (length,) = struct.unpack("<i", buf.read(4))
    if length == 0:
        return ""
    if length < 0:
        return buf.read(-length * 2).decode("utf-16-le").rstrip("\x00")
    return buf.read(length).decode("utf-8", "replace").rstrip("\x00")


def _directory_index_names(pak, index: bytes) -> list[str]:
    """Pak v10+ keep filenames in a separate full directory index."""
    buf = io.BytesIO(index)
    _read_fstring(buf)  # mount point
    buf.read(4 + 8)  # entry count, path hash seed
    (has_path_hash_index,) = struct.unpack("<I", buf.read(4))
    if has_path_hash_index:
        buf.read(8 + 8 + 20)
    (has_full_directory_index,) = struct.unpack("<I", buf.read(4))
    if not has_full_directory_index:
        return []
    offset, size = struct.unpack("<qq", buf.read(16))
    if size <= 0 or size > MAX_INDEX_BYTES:
        raise ValueError("Implausible directory index size")
    pak.seek(offset)
    directory = io.BytesIO(pak.read(size))
    names = []
    (dir_count,) = struct.unpack("<i", directory.read(4))
    for _ in range(dir_count):
        dir_name = _read_fstring(directory)
        (file_count,) = struct.unpack("<i", directory.read(4))
        for _ in range(file_count):
            names.append(dir_name + _read_fstring(directory))
            directory.read(4)
    return names


def umap_names_in_pak(path: Path) -> set[str]:
    """Returns the base names of every .umap packed in the file."""
    with path.open("rb") as pak:
        pak.seek(0, io.SEEK_END)
        file_size = pak.tell()
        pak.seek(max(0, file_size - FOOTER_SEARCH_BYTES))
        tail = pak.read()
        magic_at = tail.rfind(PAK_MAGIC)
        if magic_at < 1:
            raise ValueError(f"{path.name}: no pak footer")
        encrypted_index = tail[magic_at - 1]
        version, index_offset, index_size = struct.unpack_from("<IQQ", tail, magic_at + 4)
        if encrypted_index:
            raise ValueError(f"{path.name}: pak index is encrypted")
        if index_size > MAX_INDEX_BYTES:
            raise ValueError(f"{path.name}: implausible index size")
        pak.seek(index_offset)
        index = pak.read(index_size)

        names: list[str] = []
        if version >= 10:
            try:
                names = _directory_index_names(pak, index)
            except (ValueError, struct.error, UnicodeDecodeError):
                names = []
        if names:
            return {Path(name).stem for name in names if name.endswith(".umap")}
        # Older layouts store filenames inline in the primary index.
        return {match.decode() for match in UMAP_RE.findall(index)}


def playable(name: str) -> bool:
    match = MAP_NAME_RE.match(name)
    return bool(match) and match.group(1) not in HIDDEN_PREFIXES


def mode_of(name: str) -> str:
    return name.split("_", 1)[0]


def group_by_mode(names: set[str]) -> list[dict]:
    by_prefix: dict[str, list[str]] = {}
    for name in names:
        if playable(name):
            by_prefix.setdefault(mode_of(name), []).append(name)
    ordered = [p for p in MODE_ORDER if p in by_prefix] + sorted(p for p in by_prefix if p not in MODE_LABELS)
    return [
        {"prefix": prefix, "label": MODE_LABELS.get(prefix, prefix), "maps": sorted(by_prefix[prefix])}
        for prefix in ordered
    ]


class MapCatalog:
    """Caches the discovered maps until the pak files change (e.g. after an update)."""

    def __init__(self, paks_dir: Path):
        self.paks_dir = paks_dir
        self._signature: tuple | None = None
        self._names: set[str] = set()
        self.errors: list[str] = []

    def _current_signature(self) -> tuple:
        if not self.paks_dir.is_dir():
            return ()
        return tuple(
            (p.name, stat.st_size, stat.st_mtime_ns)
            for p in sorted(self.paks_dir.glob("*.pak"))
            for stat in [p.stat()]
        )

    def names(self, refresh: bool = False) -> set[str]:
        signature = self._current_signature()
        if refresh or signature != self._signature:
            names: set[str] = set()
            errors = []
            for pak in sorted(self.paks_dir.glob("*.pak")) if signature else []:
                try:
                    names |= umap_names_in_pak(pak)
                except (OSError, ValueError, struct.error) as exc:
                    errors.append(str(exc))
            self._names, self.errors, self._signature = names, errors, signature
        return self._names

    def modes(self, refresh: bool = False) -> list[dict]:
        return group_by_mode(self.names(refresh))
