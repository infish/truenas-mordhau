import socket
import struct
import sys
import threading
import time
import zlib
from pathlib import Path

import pytest
import uvicorn
from fastapi.testclient import TestClient

from mordhau_panel.app import Config, create_app
from mordhau_panel.rcon import RconClient

from .test_app import WRITE, panel_client

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import import_map_icons as tool  # noqa: E402

PNG = tool.encode_png([[(10, 20, 30), (40, 50, 60)], [(70, 80, 90), (100, 110, 120)]])


@pytest.fixture
def client(tmp_path):
    config = Config(panel_password="panel-pass", data_dir=tmp_path, rcon_password="x",
                    rcon=RconClient("127.0.0.1", 1, "x"))
    return panel_client(config)


def put_icon(client, name, data, **headers):
    return client.put(f"/api/map-icons/{name}", content=data, headers={**WRITE, **headers})


def test_upload_icons_and_manifest(client, tmp_path):
    assert client.get("/api/map-icons").json() == {"version": 0, "icons": {}}
    assert put_icon(client, "CampThumb.png", PNG).status_code == 200
    assert put_icon(client, "DefaultThumb.png", PNG).status_code == 200
    response = client.put("/api/map-icons", headers=WRITE,
                          json={"FFA_Camp": "CampThumb.png", "*": "DefaultThumb.png"})
    assert response.status_code == 200
    manifest = client.get("/api/map-icons").json()
    assert manifest["icons"] == {"*": "DefaultThumb.png", "FFA_Camp": "CampThumb.png"}
    assert manifest["version"] > 0

    picture = client.get("/api/map-icons/CampThumb.png")
    assert picture.status_code == 200 and picture.content == PNG
    assert picture.headers["content-type"] == "image/png"
    assert "immutable" in picture.headers["cache-control"]
    assert (tmp_path / "panel" / "map-icons" / "CampThumb.png").read_bytes() == PNG

    assert client.delete("/api/map-icons", headers=WRITE).json() == {"version": 0, "icons": {}}
    assert client.get("/api/map-icons/CampThumb.png").status_code == 404


@pytest.mark.parametrize("name, data", [
    ("../evil.png", PNG),
    ("Camp.svg", PNG),
    ("CampThumb.png", b"<svg onload=alert(1)>"),
    ("CampThumb.png", b"\x89PNG\r\n\x1a\n" + b"0" * (1024 * 1024)),
])
def test_rejects_bad_uploads(client, name, data):
    assert put_icon(client, name, data).status_code in (400, 404, 405, 413)


def test_manifest_must_reference_uploaded_pictures(client):
    put_icon(client, "CampThumb.png", PNG)
    assert client.put("/api/map-icons", headers=WRITE, json={"FFA_Camp": "Missing.png"}).status_code == 400
    assert client.put("/api/map-icons", headers=WRITE, json={"bad name!": "CampThumb.png"}).status_code == 400


def test_icons_need_login_and_panel_header(client):
    anonymous = TestClient(client.app)
    assert anonymous.get("/api/map-icons").status_code == 401
    assert anonymous.get("/api/map-icons/CampThumb.png").status_code == 401
    assert client.put("/api/map-icons/CampThumb.png", content=PNG).status_code == 403


# ---- Import tool -------------------------------------------------------------

def unpack_png(data: bytes):
    """Minimal reader for the tool's own PNGs (RGB, Sub filter)."""
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    width, height = struct.unpack(">II", data[16:24])
    idat = data[data.index(b"IDAT") + 4:data.index(b"IEND") - 8]
    raw = zlib.decompress(idat)
    rows, stride = [], width * 3 + 1
    for y in range(height):
        line = raw[y * stride:(y + 1) * stride]
        assert line[0] == 1
        values = list(line[1:])
        for i in range(3, len(values)):
            values[i] = (values[i] + values[i - 3]) & 0xFF
        rows.append([tuple(values[i:i + 3]) for i in range(0, len(values), 3)])
    return rows


def test_png_round_trip():
    pixels = [[(255, 0, 0), (0, 255, 0), (0, 0, 255)], [(1, 2, 3), (250, 251, 252), (0, 0, 0)]]
    assert unpack_png(tool.encode_png(pixels)) == pixels


def dxt1_block(c0: int, c1: int, indices: list[int]) -> bytes:
    bits = sum(index << (2 * i) for i, index in enumerate(indices))
    return struct.pack("<HHI", c0, c1, bits)


def test_dxt1_decoding():
    red, blue = 0xF800, 0x001F
    block = dxt1_block(red, blue, [0, 1, 2, 3] * 4)
    pixels = tool.decode_texture("PF_DXT1", 4, 4, block)
    assert pixels[0] == [(255, 0, 0), (0, 0, 255), (170, 0, 85), (85, 0, 170)]


def test_dxt5_uses_color_block_after_alpha():
    alpha = bytes([255, 0]) + bytes(6)
    color = dxt1_block(0x07E0, 0x07E0, [0] * 16)  # green
    assert tool.decode_texture("PF_DXT5", 4, 4, alpha + color)[3][3] == (0, 255, 0)


def test_downscale_averages():
    pixels = [[(0, 0, 0), (100, 100, 100)], [(100, 100, 100), (200, 200, 200)]]
    assert tool.downscale(pixels, 2) == [[(100, 100, 100)]]


def fstring(text: str) -> bytes:
    data = text.encode() + b"\x00"
    return struct.pack("<i", len(data)) + data


def texture_uexp(fmt: str, width: int, height: int, payload: bytes) -> bytes:
    return (b"\x00" * 16 + struct.pack("<iii", width, height, 1) + fstring(fmt)
            + struct.pack("<ii", 0, 1) + struct.pack("<iIiiq", 1, 0x48, len(payload), len(payload), 0)
            + payload + struct.pack("<iii", width, height, 1))


def test_read_texture_finds_first_mip():
    payload = dxt1_block(0xF800, 0xF800, [0] * 16)
    assert tool.read_texture(texture_uexp("PF_DXT1", 4, 4, payload)) == ("PF_DXT1", 4, 4, payload)


def uasset(names: list[str]) -> bytes:
    header = bytearray(struct.pack("<Iiiii", 0x9E2A83C1, -7, 864, 522, 0))
    header += struct.pack("<i", 0)  # custom versions
    header += struct.pack("<i", 0) + fstring("None") + struct.pack("<I", 0)
    name_offset = len(header) + 8
    header += struct.pack("<ii", len(names), name_offset)
    for name in names:
        header += fstring(name) + b"\x00" * 4
    return bytes(header)


class FakeGame:
    def __init__(self, files: dict[str, bytes]):
        self.files = files

    def names(self):
        return iter(self.files)

    def read(self, name):
        return self.files[name]


def test_map_thumbnails_prefers_specific_metadata_and_falls_back():
    base = "Mordhau/Content/Mordhau/Maps/"
    thumbs = "/Game/Mordhau/UI/UIAssets/Menu/Thumbnails/"
    game = FakeGame({
        base + "Grad/Metadata/BP_GradMapMetadata.uasset": uasset(
            [thumbs + "GradThumb", "/Game/Mordhau/Maps/Grad/FFA_Grad", "/Game/Mordhau/Maps/Grad/DIH_Grad",
             "/Game/Mordhau/Maps/Grad/TDM_Grad"]),
        base + "Grad/Metadata/BP_GradDIHOverride.uasset": uasset(
            [thumbs + "GradThumbDIH", "/Game/Mordhau/Maps/Grad/DIH_Grad"]),
        base + "Castello/Metadata/BP_CastelloMapMetadata.uasset": uasset(
            [thumbs + "CastelloThumb", "/Game/Mordhau/Maps/Castello/FFA_Castello_New"]),
        base + "Castello/Metadata/BP_CastelloLegacyOverride.uasset": uasset(
            [thumbs + "CastelloLegacyThumb", "/Game/Mordhau/Maps/Castello/FFA_CastelloLegacy"]),
        base + "Grad/TDM_Grad_64.umap": b"",
        base + "Castello/SKM_CastelloLegacy_64.umap": b"",
        base + "Moshpit/FFA_Moshpit.umap": b"",
    })
    assert tool.map_thumbnails(game) == {
        "FFA_Grad": "GradThumb", "TDM_Grad": "GradThumb", "DIH_Grad": "GradThumbDIH",
        "TDM_Grad_64": "GradThumb", "FFA_Castello_New": "CastelloThumb",
        "FFA_CastelloLegacy": "CastelloLegacyThumb", "SKM_CastelloLegacy_64": "CastelloLegacyThumb",
    }


def test_tool_uploads_to_a_real_panel(tmp_path):
    config = Config(panel_password="panel-pass", data_dir=tmp_path, rcon_password="x",
                    rcon=RconClient("127.0.0.1", 1, "x"))
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(create_app(config), host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        while not server.started:
            time.sleep(0.05)
        tool.upload(f"http://127.0.0.1:{port}", "panel-pass", {"CampThumb.png": PNG}, {"FFA_Camp": "CampThumb.png"})
        assert (tmp_path / "panel" / "map-icons" / "CampThumb.png").read_bytes() == PNG
        with pytest.raises(tool.ImportError_, match="password"):
            tool.upload(f"http://127.0.0.1:{port}", "wrong", {"CampThumb.png": PNG}, {})
    finally:
        server.should_exit = True
        thread.join(5)
