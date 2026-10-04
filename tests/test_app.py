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
    anonymous = TestClient(client.app)
    page = anonymous.get("/")
    assert page.status_code == 200 and 'id="login-form"' in page.text
    status = anonymous.get("/api/status")
    assert status.status_code == 401
    assert "www-authenticate" not in status.headers  # no native browser popup
    assert client.get("/api/status", headers=basic("admin", "nope")).status_code == 401
    assert client.get("/api/status", headers=basic("root", "panel-pass")).status_code == 401
    assert 'id="map-grid"' in client.get("/").text


def test_login_logout_with_session_cookie(client, monkeypatch):
    monkeypatch.setattr("mordhau_panel.app.FAILED_LOGIN_DELAY", 0)
    browser = TestClient(client.app)
    assert browser.post("/login", json={"password": "wrong"}, headers=WRITE).status_code == 401
    assert browser.get("/api/status").status_code == 401

    response = browser.post("/login", json={"password": "panel-pass"}, headers=WRITE)
    assert response.status_code == 200
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=strict" in cookie
    assert browser.get("/api/status").status_code == 200
    assert 'id="map-grid"' in browser.get("/").text

    browser.post("/logout", headers=WRITE)
    assert browser.get("/api/status").status_code == 401


def test_login_requires_panel_header(client):
    assert TestClient(client.app).post("/login", json={"password": "panel-pass"}).status_code == 403


def test_forged_or_expired_session_rejected(client):
    from mordhau_panel.auth import COOKIE_NAME, SessionSigner, session_key_from_password

    browser = TestClient(client.app)
    browser.cookies.set(COOKIE_NAME, "9999999999.forged")
    assert browser.get("/api/status").status_code == 401
    browser.cookies.set(COOKIE_NAME, SessionSigner(session_key_from_password("panel-pass")).issue(now=0))
    assert browser.get("/api/status").status_code == 401
    browser.cookies.set(COOKIE_NAME, SessionSigner(session_key_from_password("other-password")).issue())
    assert browser.get("/api/status").status_code == 401


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


def test_no_panel_password_means_setup_mode(monkeypatch):
    monkeypatch.delenv("PANEL_PASSWORD", raising=False)
    assert Config.from_env().panel_password is None


def test_responses_are_revalidated(client):
    assert client.get("/static/app.js").headers["cache-control"] == "no-cache"


@pytest.fixture
def players_client(data_dir):
    responses = {
        "playerlist": "10074AF86EBCB9A2, Infish1, 12 ms, team 0\nABCDEF0123456789, Guest, 80 ms, team 1\nThere are 2 bots.",
        "adminlist": "10074AF86EBCB9A2",
        "banlist": "AAAAAAAAAAAAAAAA, cheating, 1440\n",
        "getmatchduration": "Match time remaining: 600",
    }
    with FakeRconServer("rcon-pass", responses) as server:
        config = Config(panel_password="panel-pass", data_dir=data_dir, rcon_password="rcon-pass",
                        rcon=RconClient("127.0.0.1", server.port, "rcon-pass"))
        yield panel_client(config), server


def test_players_list_marks_admins(players_client):
    client, _ = players_client
    assert client.get("/api/players").json() == {
        "players": [
            {"id": "10074AF86EBCB9A2", "name": "Infish1", "ping": 12, "team": 0, "admin": True},
            {"id": "ABCDEF0123456789", "name": "Guest", "ping": 80, "team": 1, "admin": False},
        ],
        "bots": 2,
    }


def test_player_actions_send_rcon(players_client):
    client, server = players_client
    response = client.post("/api/players/ABCDEF0123456789/ban", headers=WRITE,
                           json={"reason": "team killing", "duration": 60})
    assert response.status_code == 200
    assert response.json()["command"] == "ban ABCDEF0123456789 team_killing 60"
    assert client.post("/api/players/ABCDEF0123456789/admin", headers=WRITE).status_code == 200
    assert client.post("/api/players/ABCDEF0123456789/team", headers=WRITE, json={"team": 0}).status_code == 200
    assert server.commands == [
        "ban ABCDEF0123456789 team_killing 60", "addadmin ABCDEF0123456789", "changeteam ABCDEF0123456789 0",
    ]


def test_player_action_validation(players_client):
    client, server = players_client
    assert client.post("/api/players/Guest/kick", headers=WRITE).status_code == 400
    assert client.post("/api/players/ABCDEF0123456789/shutdown", headers=WRITE).status_code == 400
    assert client.post("/api/players/ABCDEF0123456789/kick").status_code == 403  # missing panel header
    assert server.commands == []


def test_bots_say_bans_match(players_client):
    client, server = players_client
    assert client.post("/api/bots", headers=WRITE, json={"action": "add", "amount": 4, "team": 1}).status_code == 200
    assert client.post("/api/say", headers=WRITE, json={"message": "Map change in 1 min"}).status_code == 200
    assert client.post("/api/match/extend", headers=WRITE, json={"seconds": 300}).status_code == 200
    assert client.get("/api/bans").json() == {
        "entries": [{"text": "AAAAAAAAAAAAAAAA, cheating, 1440", "id": "AAAAAAAAAAAAAAAA"}],
    }
    assert client.get("/api/match").json() == {"output": "Match time remaining: 600"}
    assert server.commands[:3] == ["addbots 4 1", "say Map change in 1 min", "extendmatchduration 300"]



SETUP = {"panel_password": "new-panel-pass", "server_name": "Pisshau", "max_players": 8,
         "advertise": True, "server_password": "join me", "admin_password": ""}


@pytest.fixture
def setup_app(data_dir, rcon_server, capsys, monkeypatch):
    monkeypatch.setattr("mordhau_panel.app.FAILED_LOGIN_DELAY", 0)
    config = Config(data_dir=data_dir, rcon=RconClient("127.0.0.1", rcon_server.port, "x"))
    app = create_app(config)
    code = next(line.split(": ", 1)[1] for line in capsys.readouterr().out.splitlines() if "setup code:" in line)
    return app, code


def test_setup_flow(setup_app, data_dir):
    app, code = setup_app
    browser = TestClient(app)
    assert 'id="setup-form"' in browser.get("/").text
    assert browser.get("/api/status").json() == {"detail": "Setup required"}
    assert browser.post("/login", json={"password": "x"}, headers=WRITE).status_code == 409

    assert browser.post("/setup", json={**SETUP, "code": "WRONG-CODE"}, headers=WRITE).status_code == 401
    assert not (data_dir / "panel" / "server.env").exists()

    response = browser.post("/setup", json={**SETUP, "code": code.lower().replace("-", " ")}, headers=WRITE)
    assert response.status_code == 200
    assert (data_dir / "panel" / "server.env").read_text() == (
        "SERVER_NAME=Pisshau\nMAX_PLAYERS=8\nADVERTISE_SERVER=true\n"
        "SERVER_PASSWORD=join me\nADMIN_PASSWORD=\n"
    )
    auth_file = (data_dir / "panel" / "panel-auth.env").read_text()
    assert "new-panel-pass" not in auth_file and auth_file.startswith("PASSWORD_HASH=scrypt$")
    assert (data_dir / "panel" / "panel-auth.env").stat().st_mode & 0o777 == 0o600
    assert browser.get("/api/status").status_code == 200  # logged in by setup
    assert 'id="map-grid"' in browser.get("/").text

    assert browser.post("/setup", json={**SETUP, "code": code}, headers=WRITE).status_code == 409
    other = TestClient(app)
    assert other.post("/login", json={"password": "new-panel-pass"}, headers=WRITE).status_code == 200


def test_setup_survives_panel_restart(setup_app, data_dir, rcon_server):
    app, code = setup_app
    TestClient(app).post("/setup", json={**SETUP, "code": code}, headers=WRITE)
    restarted = create_app(Config(data_dir=data_dir, rcon=RconClient("127.0.0.1", rcon_server.port, "x")))
    browser = TestClient(restarted)
    assert 'id="login-form"' in browser.get("/").text
    assert browser.post("/login", json={"password": "new-panel-pass"}, headers=WRITE).status_code == 200


@pytest.mark.parametrize("change", [
    {"panel_password": "short"},
    {"server_name": "   "},
    {"server_name": "two\nlines"},
    {"max_players": 0},
])
def test_setup_validation(setup_app, data_dir, change):
    app, code = setup_app
    response = TestClient(app).post("/setup", json={**SETUP, **change, "code": code}, headers=WRITE)
    assert response.status_code == 400
    assert not (data_dir / "panel" / "panel-auth.env").exists()


def test_rcon_password_generated_once_and_shared(data_dir, rcon_server):
    create_app(Config(panel_password="p" * 8, data_dir=data_dir, rcon=RconClient("127.0.0.1", rcon_server.port, "x")))
    first = (data_dir / "panel" / "rcon.env").read_text()
    create_app(Config(panel_password="p" * 8, data_dir=data_dir, rcon=RconClient("127.0.0.1", rcon_server.port, "x")))
    assert (data_dir / "panel" / "rcon.env").read_text() == first
    assert len(first.strip().split("=", 1)[1]) >= 24


def test_server_settings_view_and_update(client, data_dir):
    panel = data_dir / "panel"
    panel.mkdir(exist_ok=True)
    (panel / "effective.env").write_text(
        "SERVER_NAME=From app\nMAX_PLAYERS=8\nADVERTISE_SERVER=true\n"
        "HAS_SERVER_PASSWORD=true\nHAS_ADMIN_PASSWORD=false\n")
    view = client.get("/api/server-settings").json()
    assert view == {"server_name": "From app", "max_players": 8, "advertise": True,
                    "server_password_set": True, "admin_password_set": False,
                    "saved_in_panel": [], "panel_password_managed_by": "env"}

    response = client.put("/api/server-settings", headers=WRITE, json={
        "server_name": "Renamed", "clear_server_password": True, "admin_password": "boss", "restart": True})
    assert response.status_code == 200
    body = response.json()
    assert body["server_name"] == "Renamed" and body["max_players"] == 8
    assert body["server_password_set"] is False and body["admin_password_set"] is True
    assert body["restart_pending"] is True
    assert "boss" not in response.text  # passwords are write-only
    assert (panel / "server.env").read_text() == "SERVER_NAME=Renamed\nSERVER_PASSWORD=\nADMIN_PASSWORD=boss\n"

    # Leaving a password blank keeps it.
    client.put("/api/server-settings", headers=WRITE, json={"max_players": 12, "admin_password": ""})
    assert "ADMIN_PASSWORD=boss" in (panel / "server.env").read_text()
    assert client.put("/api/server-settings", headers=WRITE, json={"max_players": 500}).status_code == 400


def test_panel_password_change(setup_app, data_dir):
    app, code = setup_app
    browser = TestClient(app)
    browser.post("/setup", json={**SETUP, "code": code}, headers=WRITE)
    other_device = TestClient(app)
    other_device.post("/login", json={"password": "new-panel-pass"}, headers=WRITE)

    assert browser.post("/api/panel-password", headers=WRITE,
                        json={"current": "wrong", "new": "another-pass"}).status_code == 401
    assert browser.post("/api/panel-password", headers=WRITE,
                        json={"current": "new-panel-pass", "new": "another-pass"}).status_code == 200
    assert browser.get("/api/status").status_code == 200  # this device stays logged in
    assert other_device.get("/api/status").status_code == 401  # others are logged out
    assert TestClient(app).post("/login", json={"password": "another-pass"}, headers=WRITE).status_code == 200


def test_env_panel_password_cannot_be_changed_in_panel(client):
    response = client.post("/api/panel-password", headers=WRITE, json={"current": "panel-pass", "new": "x" * 10})
    assert response.status_code == 409
