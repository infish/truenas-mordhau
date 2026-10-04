"""Minimal Source RCON client (the protocol Mordhau's RconPort speaks)."""

import select
import socket
import struct

SERVERDATA_AUTH = 3
SERVERDATA_AUTH_RESPONSE = 2
SERVERDATA_EXECCOMMAND = 2
SERVERDATA_RESPONSE_VALUE = 0

AUTH_ID = 1
COMMAND_ID = 2


class RconError(Exception):
    pass


class RconAuthError(RconError):
    pass


def encode_packet(request_id: int, packet_type: int, body: str) -> bytes:
    payload = struct.pack("<ii", request_id, packet_type) + body.encode("utf-8") + b"\x00\x00"
    return struct.pack("<i", len(payload)) + payload


def _recv_exact(sock: socket.socket, size: int) -> bytes:
    data = b""
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            raise RconError("RCON connection closed by server")
        data += chunk
    return data


def read_packet(sock: socket.socket) -> tuple[int, int, str]:
    (size,) = struct.unpack("<i", _recv_exact(sock, 4))
    if size < 10 or size > 1 << 20:
        raise RconError(f"Invalid RCON packet size {size}")
    payload = _recv_exact(sock, size)
    request_id, packet_type = struct.unpack("<ii", payload[:8])
    body = payload[8:].rstrip(b"\x00").decode("utf-8", "replace")
    return request_id, packet_type, body


class RconClient:
    """Opens a fresh authenticated connection per command."""

    def __init__(self, host: str, port: int, password: str, timeout: float = 5.0, idle_timeout: float = 0.3):
        self.host = host
        self.port = port
        self.password = password
        self.timeout = timeout
        self.idle_timeout = idle_timeout

    def command(self, command: str) -> str:
        if not self.password:
            raise RconError("RCON_PASSWORD is not set")
        try:
            with socket.create_connection((self.host, self.port), timeout=self.timeout) as sock:
                self._authenticate(sock)
                sock.sendall(encode_packet(COMMAND_ID, SERVERDATA_EXECCOMMAND, command))
                return self._read_response(sock)
        except TimeoutError as exc:
            raise RconError(f"RCON timed out talking to {self.host}:{self.port}") from exc
        except OSError as exc:
            raise RconError(f"Cannot reach RCON at {self.host}:{self.port}: {exc}") from exc

    def _authenticate(self, sock: socket.socket) -> None:
        sock.sendall(encode_packet(AUTH_ID, SERVERDATA_AUTH, self.password))
        # Source servers may send an empty RESPONSE_VALUE before the auth result.
        while True:
            request_id, packet_type, _ = read_packet(sock)
            if packet_type == SERVERDATA_AUTH_RESPONSE:
                if request_id == -1:
                    raise RconAuthError("RCON password was rejected")
                return

    def _read_response(self, sock: socket.socket) -> str:
        parts: list[str] = []
        while True:
            request_id, packet_type, body = read_packet(sock)
            if request_id == COMMAND_ID and packet_type == SERVERDATA_RESPONSE_VALUE:
                parts.append(body)
                break
        # Long replies are split across packets; collect until the line goes quiet.
        while select.select([sock], [], [], self.idle_timeout)[0]:
            try:
                request_id, packet_type, body = read_packet(sock)
            except RconError:
                break
            if request_id == COMMAND_ID and packet_type == SERVERDATA_RESPONSE_VALUE:
                parts.append(body)
        return "".join(parts)
