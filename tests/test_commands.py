import pytest

from mordhau_panel.commands import (
    CommandError,
    Player,
    bots_command,
    extend_match_command,
    ids_in,
    list_entries,
    parse_playerlist,
    player_command,
    say_command,
)

PLAYERLIST = (
    "10074AF86EBCB9A2, Infish1, 12 ms, team 0\n"
    "ABCDEF0123456789, Sir, Comma, 140 ms, team 1\n"
    "There are 2 bots.\n"
)


def test_parse_playerlist():
    players, bots = parse_playerlist(PLAYERLIST)
    assert players == [
        Player("10074AF86EBCB9A2", "Infish1", 12, 0),
        Player("ABCDEF0123456789", "Sir, Comma", 140, 1),
    ]
    assert bots == 2


@pytest.mark.parametrize("output, bots", [
    ("There are currently no players present", 0),
    ("There is 1 bot.", 1),
])
def test_parse_playerlist_empty(output, bots):
    assert parse_playerlist(output) == ([], bots)


def test_ids_and_list_entries():
    output = "Admins:\n10074af86ebcb9a2\n\nABCDEF0123456789 (Sir)\nno id here"
    assert ids_in(output) == {"10074AF86EBCB9A2", "ABCDEF0123456789"}
    assert list_entries(output) == [
        {"text": "Admins:", "id": None},
        {"text": "10074af86ebcb9a2", "id": "10074AF86EBCB9A2"},
        {"text": "ABCDEF0123456789 (Sir)", "id": "ABCDEF0123456789"},
        {"text": "no id here", "id": None},
    ]


ID = "10074AF86EBCB9A2"


@pytest.mark.parametrize("args, expected", [
    (("kick", ID), f"kick {ID} Kicked_by_admin"),
    (("kick", ID.lower(), "too  much\tspam"), f"kick {ID} too_much_spam"),
    (("ban", ID, "cheating", 1440), f"ban {ID} cheating 1440"),
    (("ban", ID, None, 0), f"ban {ID} Banned_by_admin 0"),
    (("mute", ID, None, 60), f"mute {ID} 60"),
    (("unmute", ID), f"unmute {ID}"),
    (("unban", ID), f"unban {ID}"),
    (("kill", ID), f"killplayer {ID}"),
    (("admin", ID), f"addadmin {ID}"),
    (("unadmin", ID), f"removeadmin {ID}"),
])
def test_player_commands(args, expected):
    assert player_command(*args) == expected


def test_team_and_rename():
    assert player_command("team", ID, team=1) == f"changeteam {ID} 1"
    assert player_command("rename", ID, name="  Sir   Knight ") == f"renameplayer {ID} Sir Knight"


@pytest.mark.parametrize("args, kwargs", [
    (("kick", "Infish1"), {}),  # names are ambiguous: target IDs only
    (("kick", f"{ID}; shutdown"), {}),
    (("ban", ID), {}),  # missing duration
    (("ban", ID, None, -1), {}),
    (("mute", ID, None, True), {}),
    (("team", ID), {"team": 5}),
    (("rename", ID), {"name": "   "}),
    (("shutdown", ID), {}),
])
def test_player_command_validation(args, kwargs):
    with pytest.raises(CommandError):
        player_command(*args, **kwargs)


def test_bots_say_extend():
    assert bots_command("add", 2) == "addbots 2"
    assert bots_command("remove", 3, 1) == "removebots 3 1"
    assert say_command("Next map\nin 5") == "say Next map in 5"
    assert extend_match_command(300) == "extendmatchduration 300"
    for bad in [lambda: bots_command("spawn", 1), lambda: bots_command("add", 0),
                lambda: bots_command("add", 1, 3), lambda: say_command(""),
                lambda: say_command("x" * 201), lambda: extend_match_command(0)]:
        with pytest.raises(CommandError):
            bad()
