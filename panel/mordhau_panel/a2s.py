"""Steam A2S_INFO query, used to show the live map and player count."""

import socket
import struct

HEADER = b"\xff\xff\xff\xff"
A2S_INFO = HEADER + b"TSource Engine Query\x00"
CHALLENGE_RESPONSE = 0x41
INFO_RESPONSE = 0x49


class QueryError(Exception):
    pass


def _read_cstring(data: bytes, offset: int) -> tuple[str, int]:
    end = data.index(b"\x00", offset)
    return data[offset:end].decode("utf-8", "replace"), end + 1


def parse_info(data: bytes) -> dict:
    if not data.startswith(HEADER) or len(data) < 6 or data[4] != INFO_RESPONSE:
        raise QueryError("Unexpected A2S_INFO response")
    offset = 6  # header + type byte + protocol byte
    name, offset = _read_cstring(data, offset)
    map_name, offset = _read_cstring(data, offset)
    _folder, offset = _read_cstring(data, offset)
    game, offset = _read_cstring(data, offset)
    offset += 2  # app id
    players, max_players, bots = struct.unpack_from("<BBB", data, offset)
    offset += 5  # players, max, bots, server type, environment
    visibility = data[offset]
    return {
        "name": name,
        "map": map_name,
        "game": game,
        "players": players,
        "max_players": max_players,
        "bots": bots,
        "password": bool(visibility),
    }


def query_info(host: str, port: int, timeout: float = 2.0) -> dict:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(timeout)
            sock.sendto(A2S_INFO, (host, port))
            data, _ = sock.recvfrom(4096)
            if len(data) >= 9 and data.startswith(HEADER) and data[4] == CHALLENGE_RESPONSE:
                sock.sendto(A2S_INFO + data[5:9], (host, port))
                data, _ = sock.recvfrom(4096)
    except OSError as exc:
        raise QueryError(f"No query response from {host}:{port}") from exc
    try:
        return parse_info(data)
    except (ValueError, IndexError, struct.error) as exc:
        raise QueryError("Malformed A2S_INFO response") from exc
