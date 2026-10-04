"""Runs server/entrypoint.sh against a fake MordhauServer binary."""

import os
import signal
import subprocess
import time
from pathlib import Path

import pytest

ENTRYPOINT = Path(__file__).resolve().parents[1] / "server" / "entrypoint.sh"

FAKE_SERVER = """#!/usr/bin/env bash
echo "start $*" >> "$FAKE_LOG"
trap 'echo stop >> "$FAKE_LOG"; exit 0' TERM
while true; do sleep 0.05; done
"""


class Harness:
    def __init__(self, root: Path, **env):
        self.root = root
        self.data = root / "data"
        self.log = root / "fake.log"
        binary_dir = self.data / "server" / "Mordhau" / "Binaries" / "Linux"
        binary_dir.mkdir(parents=True)
        binary = binary_dir / "MordhauServer-Linux-Shipping"
        binary.write_text(FAKE_SERVER)
        binary.chmod(0o755)
        (root / "home").mkdir()
        (root / "steamcmd").mkdir()
        self.env = {
            "PATH": os.environ["PATH"],
            "HOME": str(root / "home"),
            "STEAMCMDDIR": str(root / "steamcmd"),
            "SERVER_DIR": str(self.data / "server"),
            "CONFIG_DIR": str(self.data / "config"),
            "STEAMCMD_CACHE_DIR": str(self.data / "steamcmd"),
            "LOG_DIR": str(self.data / "logs"),
            "PANEL_DIR": str(self.data / "panel"),
            "UPDATE_ON_START": "false",
            "RESTART_POLL_SECONDS": "0.1",
            "FAKE_LOG": str(self.log),
            **env,
        }
        self.proc: subprocess.Popen | None = None

    @property
    def game_ini(self) -> str:
        return (self.data / "config" / "Game.ini").read_text()

    @property
    def effective(self) -> str:
        return (self.data / "panel" / "effective.env").read_text()

    def starts(self) -> list[str]:
        if not self.log.exists():
            return []
        return [line for line in self.log.read_text().splitlines() if line.startswith("start")]

    def start(self, wait=True):
        before = len(self.starts())
        # Own session so cleanup can kill the fake server child as well.
        self.proc = subprocess.Popen(["bash", str(ENTRYPOINT)], env=self.env, start_new_session=True,
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        if wait:
            self.wait_for(lambda: len(self.starts()) > before)

    def wait_for(self, condition, timeout=10.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if condition():
                return
            if self.proc and self.proc.poll() is not None:
                raise AssertionError(f"entrypoint exited early:\n{self.proc.stdout.read()}")
            time.sleep(0.05)
        raise AssertionError("timed out waiting for condition")

    def stop(self) -> int:
        self.proc.send_signal(signal.SIGTERM)
        return self.proc.wait(timeout=10)


@pytest.fixture
def harness(tmp_path):
    harnesses = []

    def make(**env):
        h = Harness(tmp_path, **env)
        harnesses.append(h)
        return h

    yield make
    for h in harnesses:
        if h.proc:
            try:
                os.killpg(h.proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def rotation_lines(game_ini: str) -> list[str]:
    return [line for line in game_ini.splitlines() if line.startswith("MapRotation=")]


def test_env_rotation_has_no_three_map_limit(harness):
    h = harness(DEFAULT_MAP="SKM_Grad", **{f"MAP_ROTATION_{i}": m for i, m in enumerate(
        ["FFA_Camp", "TDM_Camp", "SKM_Grad", "FL_Grad", "INV_Taiga_0"], start=1)})
    h.start()
    assert rotation_lines(h.game_ini) == [
        "MapRotation=FFA_Camp", "MapRotation=TDM_Camp", "MapRotation=SKM_Grad",
        "MapRotation=FL_Grad", "MapRotation=INV_Taiga_0",
    ]
    assert h.starts()[0].startswith("start Mordhau SKM_Grad ")
    assert "DEFAULT_MAP=SKM_Grad\nMAP_ROTATION=FFA_Camp,TDM_Camp,SKM_Grad,FL_Grad,INV_Taiga_0\n" in h.effective
    assert h.stop() == 0


def test_comma_separated_rotation_skips_invalid_names(harness):
    h = harness(MAP_ROTATION="FFA_Camp, TDM_Camp ,bad;name,SKM_Grad")
    h.start()
    assert rotation_lines(h.game_ini) == ["MapRotation=FFA_Camp", "MapRotation=TDM_Camp", "MapRotation=SKM_Grad"]
    assert h.starts()[0].startswith("start Mordhau FFA_ThePit ")
    h.stop()


def test_panel_restart_applies_settings_and_keeps_hand_edits(harness):
    h = harness(APPLY_ENV_ON_START="false", MAP_ROTATION="FFA_Camp,TDM_Camp")
    h.start()
    with open(h.data / "config" / "Game.ini", "a") as ini:
        ini.write("\n[/Script/Mordhau.MordhauGameMode]\nPlayerRespawnTime=3\n")

    panel = h.data / "panel"
    (panel / "settings.env").write_text("DEFAULT_MAP=TDM_Grad\nMAP_ROTATION=TDM_Grad,FL_Taiga\n")
    (panel / "restart-request").touch()
    h.wait_for(lambda: len(h.starts()) == 2)

    assert h.starts()[1].startswith("start Mordhau TDM_Grad ")
    assert "stop" in h.log.read_text()
    assert not (panel / "restart-request").exists()
    assert rotation_lines(h.game_ini) == ["MapRotation=TDM_Grad", "MapRotation=FL_Taiga"]
    assert "PlayerRespawnTime=3" in h.game_ini
    assert "ServerName=Home Mordhau" in h.game_ini
    assert "DEFAULT_MAP=TDM_Grad\nMAP_ROTATION=TDM_Grad,FL_Taiga\n" in h.effective
    assert h.stop() == 0


def test_apply_env_on_start_still_uses_panel_rotation(harness):
    h = harness(APPLY_ENV_ON_START="true", SERVER_NAME="Pisshau", MAP_ROTATION_1="FFA_Camp")
    (h.data / "panel").mkdir(parents=True)
    (h.data / "panel" / "settings.env").write_text("DEFAULT_MAP=FFA_Grad\nMAP_ROTATION=FFA_Grad,SKM_Grad\n")
    h.start()
    assert "ServerName=Pisshau" in h.game_ini
    assert rotation_lines(h.game_ini) == ["MapRotation=FFA_Grad", "MapRotation=SKM_Grad"]
    assert h.starts()[0].startswith("start Mordhau FFA_Grad ")
    h.stop()


def test_server_crash_exits_container(harness):
    h = harness()
    h.start()
    pid = int(subprocess.check_output(["pgrep", "-P", str(h.proc.pid), "-f", "MordhauServer-Linux-Shipping"],
                                      text=True).split()[0])
    os.kill(pid, signal.SIGKILL)
    assert h.proc.wait(timeout=10) == 137


def test_first_run_writes_all_sections(harness):
    h = harness(SERVER_NAME="Pisshau", MAX_PLAYERS="8", RCON_PASSWORD="r", MAP_ROTATION="FFA_Camp")
    h.start()
    assert h.game_ini == (
        "[/Script/Mordhau.MordhauGameSession]\n"
        "ServerName=Pisshau\nbAdvertiseServerViaSteam=False\nbUseOfficialBanList=True\n"
        "bUseOfficialMuteList=True\nServerPassword=\nAdminPassword=\nMaxSlots=8\n"
        "RconPassword=r\nRconPort=37001\n"
        "\n[/Script/Engine.GameSession]\nMaxPlayers=8\n"
        "\n[/Script/Mordhau.MordhauGameMode]\nMapRotation=FFA_Camp\n"
    )
    h.stop()


def test_apply_env_keeps_admins_bans_and_mutes(harness):
    h = harness(APPLY_ENV_ON_START="true", SERVER_NAME="Old", RCON_PASSWORD="r")
    h.start()
    # What the game writes after RCON addadmin/ban/mute.
    with open(h.data / "config" / "Game.ini", "a") as ini:
        ini.write("Admins=10074AF86EBCB9A2\n"
                  "BannedPlayers=(BannedPlayerId=AAAA,BanDuration=0,BanReason=\"x\")\n"
                  "MutedPlayers=(MutedPlayerId=BBBB,MuteDuration=60)\n")
    h.env.update(SERVER_NAME="New", RCON_PASSWORD="")
    (h.data / "panel" / "restart-request").touch()
    h.wait_for(lambda: len(h.starts()) == 2)

    ini = h.game_ini
    assert "Admins=10074AF86EBCB9A2" in ini
    assert "BannedPlayers=(BannedPlayerId=AAAA" in ini
    assert "MutedPlayers=(MutedPlayerId=BBBB" in ini
    assert ini.count("ServerName=") == 1
    # The env change only reaches the running loop on container restart, so the
    # name is unchanged here; RconPassword must not be duplicated either way.
    assert ini.count("RconPassword=") == 1
    h.stop()


def test_apply_env_updates_values_on_container_restart(harness):
    h = harness(APPLY_ENV_ON_START="true", SERVER_NAME="Old", RCON_PASSWORD="r")
    h.start()
    with open(h.data / "config" / "Game.ini", "a") as ini:
        ini.write("Admins=10074AF86EBCB9A2\n")
    h.stop()

    h.env.update(SERVER_NAME="New", RCON_PASSWORD="")
    h.start()
    ini = h.game_ini
    assert "ServerName=New" in ini and "ServerName=Old" not in ini
    assert "RconPassword" not in ini and "RconPort" not in ini
    assert "Admins=10074AF86EBCB9A2" in ini
    h.stop()


def write_panel_file(h, name, text):
    (h.data / "panel").mkdir(parents=True, exist_ok=True)
    (h.data / "panel" / name).write_text(text)


def test_server_env_overrides_per_key_and_reverts(harness):
    h = harness(SERVER_NAME="From env", MAX_PLAYERS="8", ADMIN_PASSWORD="env-admin")
    write_panel_file(h, "server.env", "SERVER_NAME=From panel = with equals\nSERVER_PASSWORD=join\n")
    h.start()
    ini = h.game_ini
    assert "ServerName=From panel = with equals" in ini
    assert "ServerPassword=join" in ini
    assert "AdminPassword=env-admin" in ini  # not in server.env: env value stays
    assert "MaxSlots=8" in ini
    effective = h.effective
    assert "SERVER_NAME=From panel = with equals" in effective
    assert "HAS_SERVER_PASSWORD=true" in effective and "HAS_ADMIN_PASSWORD=true" in effective
    assert "=join" not in effective and "env-admin" not in effective  # no secrets

    write_panel_file(h, "server.env", "SERVER_PASSWORD=\n")
    (h.data / "panel" / "restart-request").touch()
    h.wait_for(lambda: len(h.starts()) == 2)
    h.wait_for(lambda: "ServerName=From env" in h.game_ini)
    assert "ServerPassword=\n" in h.game_ini
    h.stop()


def test_rcon_password_from_panel_file(harness):
    h = harness()
    write_panel_file(h, "rcon.env", "RCON_PASSWORD=generated+/=\n")
    h.start()
    assert "RconPassword=generated+/=" in h.game_ini
    assert "HAS_RCON=true" in h.effective
    h.stop()


def test_env_rcon_password_wins_over_file(harness):
    h = harness(RCON_PASSWORD="from-env")
    write_panel_file(h, "rcon.env", "RCON_PASSWORD=from-file\n")
    h.start()
    assert "RconPassword=from-env" in h.game_ini
    h.stop()


def test_waits_for_setup_before_first_start(harness):
    h = harness(WAIT_FOR_SETUP="true")
    h.start(wait=False)
    time.sleep(0.6)
    assert h.starts() == []
    assert not (h.data / "config" / "Game.ini").exists()

    write_panel_file(h, "server.env", "SERVER_NAME=After setup\nMAX_PLAYERS=12\n")
    h.wait_for(lambda: len(h.starts()) == 1)
    assert "ServerName=After setup" in h.game_ini and "MaxSlots=12" in h.game_ini
    assert h.stop() == 0


def test_stop_while_waiting_for_setup(harness):
    h = harness(WAIT_FOR_SETUP="true")
    h.start(wait=False)
    time.sleep(0.3)
    assert h.stop() == 0
