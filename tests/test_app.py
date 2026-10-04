import base64

import pytest
from fastapi.testclient import TestClient

from mordhau_panel.app import Config, create_app
from mordhau_panel.rcon import RconClient

from .fakes import FakeA2SServer, FakeRconServer
from .test_maps import write_v11_pak

WRITE = {"X-Panel-Request": "1"}


def basic(username: str, password: str) -> dict:
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def panel_client(config: Config) -> TestClient:
    return TestClient(create_app(config), headers=basic("admin", "panel-pass"))


@pytest.fixture
def rcon_server():
    with FakeRconServer("rcon-pass", {"changelevel": "Changing map"}) as server:
        yield server


@pytest.fixture
def data_dir(tmp_path):
    paks = tmp_path / "server" / "Mordhau" / "Content" / "Paks"
    paks.mkdir(parents=True)
    write_v11_pak(paks / "pakchunk0-LinuxServer.pak", {
        "Maps/": ["FFA_Camp.umap", "TDM_Camp.umap", "SKM_Grad.umap", "Camp.umap"],
    })
    return tmp_path


@pytest.fixture
def client(data_dir, rcon_server):
    config = Config(
        panel_password="panel-pass",
        data_dir=data_dir,
        rcon_password="rcon-pass",
        query_host="127.0.0.1",
        query_port=1,
        rcon=RconClient("127.0.0.1", rcon_server.port, "rcon-pass"),
    )
    return panel_client(config)


def test_requires_auth(client):
    assert TestClient(client.app).get("/").status_code == 401
    assert client.get("/api/status", headers=basic("admin", "nope")).status_code == 401
    assert client.get("/api/status", headers=basic("root", "panel-pass")).status_code == 401
    assert client.get("/").status_code == 200


def test_writes_require_panel_header(client, rcon_server):
    response = client.post("/api/changelevel", json={"map": "FFA_Camp"})
    assert response.status_code == 403
    assert rcon_server.commands == []


def test_lists_maps_by_mode(client):
    modes = client.get("/api/maps").json()["modes"]
    assert [(m["prefix"], m["maps"]) for m in modes] == [
        ("FFA", ["FFA_Camp"]),
        ("TDM", ["TDM_Camp"]),
        ("SKM", ["SKM_Grad"]),
    ]


def test_changelevel_sends_rcon(client, rcon_server):
    response = client.post("/api/changelevel", json={"map": "TDM_Camp"}, headers=WRITE)
    assert response.status_code == 200
    assert response.json() == {"output": "Changing map"}
    assert rcon_server.commands == ["changelevel TDM_Camp"]


@pytest.mark.parametrize("bad", ["FFA_Camp; quit", "FFA Camp", "", "../x"])
def test_changelevel_rejects_bad_names(client, rcon_server, bad):
    assert client.post("/api/changelevel", json={"map": bad}, headers=WRITE).status_code == 400
    assert rcon_server.commands == []


def test_rcon_failure_is_reported(data_dir):
    config = Config(panel_password="panel-pass", data_dir=data_dir, rcon_password="x",
                    rcon=RconClient("127.0.0.1", 1, "x", timeout=0.5))
    client = panel_client(config)
    response = client.post("/api/console", json={"command": "help"}, headers=WRITE)
    assert response.status_code == 502
    assert "Cannot reach RCON" in response.json()["detail"]


def test_console(client, rcon_server):
    assert client.post("/api/console", json={"command": " playerlist "}, headers=WRITE).json() == {
        "output": "ran playerlist"
    }
    assert client.post("/api/console", json={"command": "a\nb"}, headers=WRITE).status_code == 400


def test_save_settings_and_restart(client, data_dir):
    response = client.put("/api/settings", headers=WRITE, json={
        "default_map": "TDM_Camp", "rotation": ["TDM_Camp", "FFA_Camp", "SKM_Grad", "FFA_Camp"], "restart": True,
    })
    assert response.status_code == 200
    panel = data_dir / "panel"
    assert (panel / "settings.env").read_text() == (
        "DEFAULT_MAP=TDM_Camp\nMAP_ROTATION=TDM_Camp,FFA_Camp,SKM_Grad,FFA_Camp\n"
    )
    assert (panel / "restart-request").exists()
    assert response.json()["restart_pending"] is True
    assert response.json()["saved"] == {
        "default_map": "TDM_Camp", "rotation": ["TDM_Camp", "FFA_Camp", "SKM_Grad", "FFA_Camp"],
    }

    assert client.delete("/api/settings", headers=WRITE).json()["saved"] is None
    assert not (panel / "settings.env").exists()


@pytest.mark.parametrize("body", [
    {"default_map": "FFA_Camp", "rotation": []},
    {"default_map": "FFA Camp", "rotation": ["FFA_Camp"]},
    {"default_map": "FFA_Camp", "rotation": ["FFA_Camp\nRconPassword=x"]},
])
def test_save_settings_validates(client, data_dir, body):
    assert client.put("/api/settings", json=body, headers=WRITE).status_code == 400
    assert not (data_dir / "panel" / "settings.env").exists()


def test_status_reports_server_and_effective_settings(data_dir, rcon_server):
    panel = data_dir / "panel"
    panel.mkdir()
    (panel / "effective.env").write_text("DEFAULT_MAP=FFA_Camp\nMAP_ROTATION=FFA_Camp,TDM_Camp\nSTARTED_AT=1700000000\n")
    with FakeA2SServer(name="Pisshau", map_name="FFA_Camp", players=1, max_players=8) as a2s:
        config = Config(panel_password="panel-pass", data_dir=data_dir, rcon_password="rcon-pass",
                        query_host="127.0.0.1", query_port=a2s.port)
        data = panel_client(config).get("/api/status").json()
    assert data["server"]["online"] is True
    assert data["server"]["map"] == "FFA_Camp"
    assert data["rcon_configured"] is True
    assert data["settings"] == {
        "saved": None,
        "effective": {"default_map": "FFA_Camp", "rotation": ["FFA_Camp", "TDM_Camp"], "started_at": 1700000000},
        "restart_pending": False,
    }


def test_status_when_server_offline(client):
    server = client.get("/api/status").json()["server"]
    assert server["online"] is False


def test_missing_panel_password_refuses_to_start(monkeypatch):
    monkeypatch.delenv("PANEL_PASSWORD", raising=False)
    with pytest.raises(SystemExit):
        Config.from_env()


def test_responses_are_revalidated(client):
    assert client.get("/static/app.js").headers["cache-control"] == "no-cache"
