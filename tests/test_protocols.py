import socket

import pytest

from mordhau_panel.a2s import QueryError, query_info
from mordhau_panel.rcon import RconAuthError, RconClient, RconError

from .fakes import FakeA2SServer, FakeRconServer


def test_rcon_runs_command():
    with FakeRconServer("secret", {"changelevel": "Changing level"}) as server:
        client = RconClient("127.0.0.1", server.port, "secret")
        assert client.command("changelevel FFA_Camp") == "Changing level"
        assert server.commands == ["changelevel FFA_Camp"]


def test_rcon_joins_split_replies():
    long_reply = "".join(f"player{i}\n" for i in range(2000))
    with FakeRconServer("secret", {"playerlist": long_reply}, chunk_size=1000) as server:
        assert RconClient("127.0.0.1", server.port, "secret").command("playerlist") == long_reply


def test_rcon_rejects_wrong_password():
    with FakeRconServer("secret") as server:
        with pytest.raises(RconAuthError):
            RconClient("127.0.0.1", server.port, "wrong").command("help")


def test_rcon_requires_password():
    with pytest.raises(RconError, match="RCON_PASSWORD"):
        RconClient("127.0.0.1", 1, "").command("help")


def test_rcon_unreachable():
    with socket.create_server(("127.0.0.1", 0)) as sock:
        port = sock.getsockname()[1]
    with pytest.raises(RconError, match="Cannot reach"):
        RconClient("127.0.0.1", port, "secret", timeout=1).command("help")


def test_a2s_info_with_challenge():
    with FakeA2SServer(name="Pisshau", map_name="TDM_Camp", players=3, max_players=8) as server:
        info = query_info("127.0.0.1", server.port)
    assert info == {
        "name": "Pisshau",
        "map": "TDM_Camp",
        "game": "Mordhau",
        "players": 3,
        "max_players": 8,
        "bots": 0,
        "password": True,
    }


def test_a2s_timeout():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as silent:
        silent.bind(("127.0.0.1", 0))
        with pytest.raises(QueryError):
            query_info("127.0.0.1", silent.getsockname()[1], timeout=0.2)
