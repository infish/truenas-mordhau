"""Builds Mordhau RCON commands from validated input and parses their output."""

import re
from dataclasses import dataclass

PLAYFAB_ID_RE = re.compile(r"^[0-9A-Fa-f]{8,32}$")
PLAYFAB_ID_IN_TEXT_RE = re.compile(r"\b[0-9A-Fa-f]{16}\b")
# "<PlayFabID>, <Name>, <ping> ms, team <n>"; names may contain commas.
PLAYER_LINE_RE = re.compile(r"^(?P<id>[0-9A-Fa-f]{8,32}), (?P<name>.*), (?P<ping>\d+) ms, team (?P<team>-?\d+)\s*$")
BOTS_RE = re.compile(r"There (?:are|is) (\d+) bots?", re.IGNORECASE)

MAX_TEXT = 200
MAX_DURATION = 10 * 365 * 24 * 60
MAX_BOTS = 64
TEAMS = (0, 1)


class CommandError(ValueError):
    pass


@dataclass
class Player:
    id: str
    name: str
    ping: int
    team: int


def parse_playerlist(output: str) -> tuple[list[Player], int]:
    players = []
    bots = 0
    for line in output.splitlines():
        match = PLAYER_LINE_RE.match(line.strip())
        if match:
            players.append(Player(match["id"].upper(), match["name"], int(match["ping"]), int(match["team"])))
            continue
        bots_match = BOTS_RE.search(line)
        if bots_match:
            bots = int(bots_match.group(1))
    return players, bots


def ids_in(output: str) -> set[str]:
    return {match.upper() for match in PLAYFAB_ID_IN_TEXT_RE.findall(output)}


def list_entries(output: str) -> list[dict]:
    """Splits banlist/mutelist output into lines, tagging any PlayFab ID found."""
    entries = []
    for line in output.splitlines():
        if not line.strip():
            continue
        found = PLAYFAB_ID_IN_TEXT_RE.search(line)
        entries.append({"text": line.strip(), "id": found.group(0).upper() if found else None})
    return entries


def player_id(value: str) -> str:
    if not isinstance(value, str) or not PLAYFAB_ID_RE.match(value):
        raise CommandError("Invalid PlayFab ID")
    return value.upper()


def text(value: str | None, field: str, required: bool = True) -> str:
    """One line of free text (messages, new names); RCON reads it to the end."""
    cleaned = " ".join((value or "").split())
    if required and not cleaned:
        raise CommandError(f"{field} is required")
    if len(cleaned) > MAX_TEXT:
        raise CommandError(f"{field} is limited to {MAX_TEXT} characters")
    return cleaned


def word(value: str | None, default: str) -> str:
    """A reason squeezed into one token, because ban takes the duration after it."""
    cleaned = "_".join((value or "").split())[:MAX_TEXT]
    return cleaned or default


def bounded_int(value, field: str, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise CommandError(f"{field} must be a whole number from {low} to {high}")
    return value


def player_command(action: str, target: str, reason: str | None = None, duration: int | None = None,
                   team: int | None = None, name: str | None = None) -> str:
    target = player_id(target)
    if action == "kick":
        return f"kick {target} {word(reason, 'Kicked_by_admin')}"
    if action == "ban":
        minutes = bounded_int(duration, "Duration", 0, MAX_DURATION)
        return f"ban {target} {word(reason, 'Banned_by_admin')} {minutes}"
    if action == "mute":
        return f"mute {target} {bounded_int(duration, 'Duration', 0, MAX_DURATION)}"
    if action == "unmute":
        return f"unmute {target}"
    if action == "unban":
        return f"unban {target}"
    if action == "kill":
        return f"killplayer {target}"
    if action == "admin":
        return f"addadmin {target}"
    if action == "unadmin":
        return f"removeadmin {target}"
    if action == "team":
        if team not in TEAMS:
            raise CommandError(f"Team must be one of {TEAMS}")
        return f"changeteam {target} {team}"
    if action == "rename":
        return f"renameplayer {target} {text(name, 'New name')}"
    raise CommandError(f"Unknown action {action!r}")


def bots_command(action: str, amount: int, team: int | None = None) -> str:
    if action not in ("add", "remove"):
        raise CommandError("Bot action must be add or remove")
    amount = bounded_int(amount, "Amount", 1, MAX_BOTS)
    if team is not None and team not in TEAMS:
        raise CommandError(f"Team must be one of {TEAMS}")
    command = f"{action}bots {amount}"
    return command if team is None else f"{command} {team}"


def say_command(message: str) -> str:
    return f"say {text(message, 'Message')}"


def extend_match_command(seconds: int) -> str:
    return f"extendmatchduration {bounded_int(seconds, 'Seconds', 1, 24 * 3600)}"
