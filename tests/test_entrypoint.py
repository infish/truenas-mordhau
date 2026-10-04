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

    def start(self):
        self.proc = subprocess.Popen(["bash", str(ENTRYPOINT)], env=self.env,
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        self.wait_for(lambda: len(self.starts()) >= 1)

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
        if h.proc and h.proc.poll() is None:
            h.proc.kill()


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
    pid = int(subprocess.check_output(["pgrep", "-f", "MordhauServer-Linux-Shipping Mordhau"], text=True).split()[0])
    os.kill(pid, signal.SIGKILL)
    assert h.proc.wait(timeout=10) == 137
