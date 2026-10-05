#!/usr/bin/env python3
"""Imports Mordhau's official map pictures into your Mordhau panel.

The pictures are Triternion's artwork, so this project does not ship them.
This tool reads them from a Mordhau game install on your computer (Steam or
Epic) and uploads them to your own panel. It needs only Python 3.8+.

    python3 import_map_icons.py --panel http://192.168.1.50:37080

It finds the game automatically in the usual Steam/Heroic/Epic folders; pass
--game "<Mordhau install folder>" if it does not. Use --output <folder> to
only save the pictures without uploading.
"""

from __future__ import annotations

import argparse
import base64
import getpass
import io
import json
import os
import re
import struct
import sys
import urllib.error
import urllib.request
import zlib
from pathlib import Path

PAK_MAGIC = struct.pack("<I", 0x5A6F12E1)
UASSET_MAGIC = 0x9E2A83C1
ENTRY_HEADER = 53  # serialized FPakEntry before uncompressed file data (pak v11)
THUMBS_DIR = "Mordhau/Content/Mordhau/UI/UIAssets/Menu/Thumbnails/"
LEVEL_RE = re.compile(r"^[A-Z]{2,3}_[A-Za-z0-9_]+$")
DEFAULT_THUMB = "DefaultThumb"
ICON_SCALE = 2  # 512x264 thumbnails become 256x132 icons

COMMON_GAME_DIRS = [
    "~/.steam/debian-installation/steamapps/common/Mordhau",
    "~/.steam/steam/steamapps/common/Mordhau",
    "~/.local/share/Steam/steamapps/common/Mordhau",
    "~/.var/app/com.valvesoftware.Steam/.local/share/Steam/steamapps/common/Mordhau",
    "~/Games/Heroic/Mordhau",
    "C:/Program Files (x86)/Steam/steamapps/common/Mordhau",
    "C:/Program Files/Epic Games/Mordhau",
    "~/Library/Application Support/Steam/steamapps/common/Mordhau",
]


class ImportError_(Exception):
    pass


# ---- Pak reading -----------------------------------------------------------

def read_fstring(buf: io.BytesIO) -> str:
    (length,) = struct.unpack("<i", buf.read(4))
    if length == 0:
        return ""
    if length < 0:
        return buf.read(-length * 2).decode("utf-16-le").rstrip("\x00")
    return buf.read(length).decode("utf-8", "replace").rstrip("\x00")


class Pak:
    """Reads the file index of an unencrypted UE4 pak (version 10 or 11)."""

    def __init__(self, path: Path):
        self.path = path
        self.files: dict[str, tuple[int, int, int, bool]] = {}
        with path.open("rb") as pak:
            pak.seek(0, io.SEEK_END)
            size = pak.tell()
            pak.seek(max(0, size - 1024))
            tail = pak.read()
            at = tail.rfind(PAK_MAGIC)
            if at < 1:
                raise ImportError_(f"{path.name}: not a pak file")
            version, index_offset, index_size = struct.unpack_from("<IQQ", tail, at + 4)
            if tail[at - 1]:
                raise ImportError_(f"{path.name}: encrypted index")
            if version < 10:
                raise ImportError_(f"{path.name}: unsupported pak version {version}")
            pak.seek(index_offset)
            index = io.BytesIO(pak.read(index_size))
            mount = read_fstring(index).replace("../../../", "")
            index.read(4 + 8)  # entry count, path hash seed
            if struct.unpack("<I", index.read(4))[0]:
                index.read(8 + 8 + 20)
            if not struct.unpack("<I", index.read(4))[0]:
                return
            dir_offset, dir_size = struct.unpack("<qq", index.read(16))
            index.read(20)
            (encoded_size,) = struct.unpack("<i", index.read(4))
            encoded = index.read(encoded_size)
            pak.seek(dir_offset)
            directory = io.BytesIO(pak.read(dir_size))
            for _ in range(struct.unpack("<i", directory.read(4))[0]):
                dir_name = read_fstring(directory)
                for _ in range(struct.unpack("<i", directory.read(4))[0]):
                    file_name = read_fstring(directory)
                    (entry_at,) = struct.unpack("<i", directory.read(4))
                    if entry_at >= 0:
                        self.files[mount + dir_name + file_name] = self._decode_entry(encoded, entry_at)

    @staticmethod
    def _decode_entry(encoded: bytes, at: int) -> tuple[int, int, int, bool]:
        buf = io.BytesIO(encoded[at:])
        (bits,) = struct.unpack("<I", buf.read(4))
        compression = (bits >> 23) & 0x3F
        encrypted = bool((bits >> 22) & 1)
        offset = struct.unpack("<I" if bits & (1 << 31) else "<Q", buf.read(4 if bits & (1 << 31) else 8))[0]
        size = struct.unpack("<I" if bits & (1 << 30) else "<Q", buf.read(4 if bits & (1 << 30) else 8))[0]
        return offset, size, compression, encrypted

    def read(self, name: str) -> bytes:
        offset, size, compression, encrypted = self.files[name]
        if compression or encrypted:
            raise ImportError_(f"{name}: compressed or encrypted files are not supported")
        with self.path.open("rb") as pak:
            pak.seek(offset + ENTRY_HEADER)
            return pak.read(size)


class Game:
    def __init__(self, paks_dir: Path):
        self.paks = []
        for path in sorted(paks_dir.glob("*.pak")):
            try:
                self.paks.append(Pak(path))
            except (ImportError_, OSError, struct.error) as exc:
                print(f"  skipping {path.name}: {exc}")
        if not self.paks:
            raise ImportError_(f"No readable .pak files in {paks_dir}")

    def names(self):
        for pak in self.paks:
            yield from pak.files

    def read(self, name: str) -> bytes:
        for pak in self.paks:
            if name in pak.files:
                return pak.read(name)
        raise KeyError(name)


def uasset_names(data: bytes) -> list[str]:
    buf = io.BytesIO(data)
    tag, legacy = struct.unpack("<Ii", buf.read(8))
    if tag != UASSET_MAGIC:
        raise ImportError_("not a uasset")
    if legacy != -4:
        buf.read(4)
    buf.read(8)
    (custom_versions,) = struct.unpack("<i", buf.read(4))
    buf.read(custom_versions * 20)
    buf.read(4)
    read_fstring(buf)
    buf.read(4)
    count, offset = struct.unpack("<ii", buf.read(8))
    buf.seek(offset)
    names = []
    for _ in range(count):
        names.append(read_fstring(buf))
        buf.read(4)
    return names


# ---- Textures ----------------------------------------------------------------

def rgb565(value: int) -> tuple[int, int, int]:
    r, g, b = (value >> 11) & 0x1F, (value >> 5) & 0x3F, value & 0x1F
    return (r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2)


def decode_color_block(block: bytes, four_colors_only: bool) -> list[tuple[int, int, int, int]]:
    c0, c1, indices = struct.unpack("<HHI", block)
    a, b = rgb565(c0), rgb565(c1)
    if c0 > c1 or four_colors_only:
        palette = [a + (255,), b + (255,),
                   tuple((2 * x + y) // 3 for x, y in zip(a, b)) + (255,),
                   tuple((x + 2 * y) // 3 for x, y in zip(a, b)) + (255,)]
    else:
        palette = [a + (255,), b + (255,), tuple((x + y) // 2 for x, y in zip(a, b)) + (255,), (0, 0, 0, 0)]
    return [palette[(indices >> (2 * i)) & 3] for i in range(16)]


def decode_alpha_block(block: bytes) -> list[int]:
    a0, a1 = block[0], block[1]
    bits = int.from_bytes(block[2:8], "little")
    if a0 > a1:
        palette = [a0, a1] + [((7 - i) * a0 + i * a1) // 7 for i in range(1, 7)]
    else:
        palette = [a0, a1] + [((5 - i) * a0 + i * a1) // 5 for i in range(1, 5)] + [0, 255]
    return [palette[(bits >> (3 * i)) & 7] for i in range(16)]


def decode_texture(fmt: str, width: int, height: int, data: bytes) -> list[list[tuple[int, int, int]]]:
    """Returns rows of RGB pixels."""
    pixels = [[(0, 0, 0)] * width for _ in range(height)]
    if fmt == "PF_B8G8R8A8":
        for y in range(height):
            row = data[y * width * 4:(y + 1) * width * 4]
            pixels[y] = [(row[i + 2], row[i + 1], row[i]) for i in range(0, len(row), 4)]
        return pixels
    if fmt not in ("PF_DXT1", "PF_DXT5"):
        raise ImportError_(f"unsupported texture format {fmt}")
    block_size = 8 if fmt == "PF_DXT1" else 16
    blocks_x, blocks_y = (width + 3) // 4, (height + 3) // 4
    if len(data) < blocks_x * blocks_y * block_size:
        raise ImportError_("texture data is truncated")
    at = 0
    for by in range(blocks_y):
        for bx in range(blocks_x):
            if fmt == "PF_DXT1":
                texels = decode_color_block(data[at:at + 8], False)
            else:
                texels = decode_color_block(data[at + 8:at + 16], True)
            at += block_size
            for i, (r, g, b, _a) in enumerate(texels):
                x, y = bx * 4 + i % 4, by * 4 + i // 4
                if x < width and y < height:
                    pixels[y][x] = (r, g, b)
    return pixels


def read_texture(uexp: bytes) -> tuple[str, int, int, bytes]:
    """Finds the first (largest) mip of a cooked UTexture2D in its .uexp."""
    match = re.search(rb"PF_[A-Z0-9_]+\x00", uexp)
    if not match:
        raise ImportError_("no pixel format found")
    fmt = match.group(0)[:-1].decode()
    at = match.start() - 4
    width, height, _packed = struct.unpack_from("<iii", uexp, at - 12)
    pos = match.end()
    _first_mip, mip_count = struct.unpack_from("<ii", uexp, pos)
    pos += 8
    if mip_count < 1:
        raise ImportError_("texture has no mips")
    _cooked, flags = struct.unpack_from("<iI", uexp, pos)
    pos += 8
    if flags & 0x2000:  # 64-bit sizes
        count, _disk = struct.unpack_from("<qq", uexp, pos)
        pos += 16
    else:
        count, _disk = struct.unpack_from("<ii", uexp, pos)
        pos += 8
    pos += 8  # offset in file
    if flags & 0x100:  # payload in a separate .ubulk file
        raise ImportError_("texture data is stored outside the asset")
    return fmt, width, height, uexp[pos:pos + count]


def downscale(pixels, factor: int):
    height, width = len(pixels) // factor, len(pixels[0]) // factor
    out = []
    area = factor * factor
    for y in range(height):
        rows = pixels[y * factor:(y + 1) * factor]
        row = []
        for x in range(width):
            r = g = b = 0
            for source in rows:
                for pr, pg, pb in source[x * factor:(x + 1) * factor]:
                    r += pr; g += pg; b += pb
            row.append((r // area, g // area, b // area))
        out.append(row)
    return out


def encode_png(pixels) -> bytes:
    height, width = len(pixels), len(pixels[0])
    raw = bytearray()
    for row in pixels:
        raw.append(1)  # "Sub" filter: store the difference to the pixel on the left
        previous = (0, 0, 0)
        for pixel in row:
            raw.extend(((c - p) & 0xFF) for c, p in zip(pixel, previous))
            previous = pixel

    def chunk(kind: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b""))


# ---- Which picture belongs to which map --------------------------------------

def map_thumbnails(game: Game) -> dict[str, str]:
    """Maps each level (e.g. "TDM_Camp_64") to its thumbnail asset name.

    Every map has metadata assets listing its levels and its thumbnail. When a
    level appears in several (a base asset plus a DIH/Legacy override), the
    most specific one (fewest levels) that has a thumbnail wins.
    """
    candidates: dict[str, list[tuple[int, str]]] = {}
    folder_thumb: dict[str, tuple[int, str]] = {}  # map folder -> picture of its main metadata
    for name in game.names():
        if not (name.endswith(".uasset") and "/Maps/" in name and "/Metadata/" in name):
            continue
        folder = name.split("/Maps/", 1)[1].split("/", 1)[0]
        refs = uasset_names(game.read(name))
        thumbs = sorted({r.rsplit("/", 1)[1] for r in refs if "/Thumbnails/" in r and "." not in r})
        levels = {r.rsplit("/", 1)[1] for r in refs
                  if r.startswith("/Game/Mordhau/Maps/") and "." not in r and LEVEL_RE.match(r.rsplit("/", 1)[1])}
        if thumbs:
            for level in levels:
                candidates.setdefault(level, []).append((len(levels), thumbs[0]))
            if len(levels) > folder_thumb.get(folder, (-1, ""))[0]:
                folder_thumb[folder] = (len(levels), thumbs[0])
    result = {level: min(options)[1] for level, options in candidates.items()}
    # Levels no metadata lists with a picture (e.g. TDM_Camp_64, INV_Grad_0):
    # prefer a picture named like the level ("CastelloLegacyThumb" for
    # SKM_CastelloLegacy_64), else the main picture of the level's map folder.
    by_name = {t[:-len("Thumb")]: t for _, t in folder_thumb.values() if t.endswith("Thumb")}
    by_name.update({t[:-len("Thumb")]: t for options in candidates.values() for _, t in options
                    if t.endswith("Thumb")})
    for name in game.names():
        if not (name.endswith(".umap") and "/Maps/" in name):
            continue
        level = name.rsplit("/", 1)[1][:-len(".umap")]
        if not LEVEL_RE.match(level) or level in result:
            continue
        base = level.split("_", 1)[1]
        named = [key for key in by_name if base.startswith(key)]
        folder = name.split("/Maps/", 1)[1].split("/", 1)[0]
        if named:
            result[level] = by_name[max(named, key=len)]
        elif folder in folder_thumb:
            result[level] = folder_thumb[folder][1]
    return result


def find_game(explicit: str | None) -> Path:
    options = [explicit] if explicit else COMMON_GAME_DIRS
    for option in options:
        root = Path(os.path.expanduser(option))
        for paks in (root / "Mordhau/Content/Paks", root / "Content/Paks", root):
            if any(paks.glob("pakchunk*.pak")):
                return paks
    if explicit:
        raise ImportError_(f"No Mordhau .pak files found under {explicit}")
    raise ImportError_("Mordhau was not found. Pass --game \"<Mordhau install folder>\".")


def build_icons(game: Game) -> tuple[dict[str, bytes], dict[str, str]]:
    level_thumbs = map_thumbnails(game)
    wanted = sorted(set(level_thumbs.values()) | {DEFAULT_THUMB})
    icons = {}
    for thumb in wanted:
        try:
            fmt, width, height, data = read_texture(game.read(f"{THUMBS_DIR}{thumb}.uexp"))
            pixels = downscale(decode_texture(fmt, width, height, data), ICON_SCALE)
        except (KeyError, ImportError_, struct.error) as exc:
            print(f"  skipping {thumb}: {exc}")
            continue
        icons[f"{thumb}.png"] = encode_png(pixels)
        print(f"  {thumb}: {width}x{height} {fmt}")
    manifest = {level: f"{thumb}.png" for level, thumb in sorted(level_thumbs.items()) if f"{thumb}.png" in icons}
    if f"{DEFAULT_THUMB}.png" in icons:
        manifest["*"] = f"{DEFAULT_THUMB}.png"
    return icons, manifest


# ---- Upload ------------------------------------------------------------------

def upload(panel: str, password: str, icons: dict[str, bytes], manifest: dict[str, str]) -> None:
    token = base64.b64encode(f"admin:{password}".encode()).decode()
    headers = {"Authorization": f"Basic {token}", "X-Panel-Request": "1"}

    def send(path: str, body: bytes, content_type: str) -> None:
        request = urllib.request.Request(panel.rstrip("/") + path, data=body, method="PUT",
                                         headers={**headers, "Content-Type": content_type})
        try:
            with urllib.request.urlopen(request, timeout=30):
                pass
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")
            if exc.code == 401:
                raise ImportError_("The panel rejected the password.") from exc
            raise ImportError_(f"Upload of {path} failed ({exc.code}): {detail}") from exc
        except urllib.error.URLError as exc:
            raise ImportError_(f"Cannot reach the panel at {panel}: {exc.reason}") from exc

    for name, data in icons.items():
        send(f"/api/map-icons/{name}", data, "image/png")
    send("/api/map-icons", json.dumps(manifest).encode(), "application/json")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--panel", help="panel address, e.g. http://192.168.1.50:37080")
    parser.add_argument("--game", help="Mordhau install folder (found automatically if omitted)")
    parser.add_argument("--output", help="save the pictures to this folder instead of uploading")
    args = parser.parse_args()
    if not args.panel and not args.output:
        parser.error("give --panel <address> to upload, or --output <folder> to save")

    try:
        paks = find_game(args.game)
        print(f"Reading Mordhau from {paks}")
        icons, manifest = build_icons(Game(paks))
        if not icons:
            raise ImportError_("No map pictures could be read.")
        print(f"Found {len(icons)} pictures for {len(manifest)} maps.")
        if args.output:
            out = Path(args.output)
            out.mkdir(parents=True, exist_ok=True)
            for name, data in icons.items():
                (out / name).write_bytes(data)
            (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
            print(f"Saved to {out}")
        if args.panel:
            password = os.environ.get("PANEL_PASSWORD") or getpass.getpass("Panel password: ")
            upload(args.panel, password, icons, manifest)
            print("Uploaded. Reload the panel to see the pictures.")
    except ImportError_ as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
