"""In-process fakes for the Source RCON and A2S protocols."""

import socket
import struct
import threading

from mordhau_panel.rcon import (
    SERVERDATA_AUTH,
    SERVERDATA_AUTH_RESPONSE,
    SERVERDATA_RESPONSE_VALUE,
    encode_packet,
    read_packet,
)


class FakeRconServer:
    """Answers commands from `responses` (a string, or a callable taking the full
    command); replies longer than chunk_size are split."""

    def __init__(self, password: str, responses: dict[str, str] | None = None, chunk_size: int = 4000):
        self.password = password
        self.responses = responses or {}
        self.chunk_size = chunk_size
        self.commands: list[str] = []
        self._sock = socket.create_server(("127.0.0.1", 0))
        self.port = self._sock.getsockname()[1]
        self._thread = threading.Thread(target=self._serve, daemon=True)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._sock.close()

    def _serve(self):
        while True:
            try:
                conn, _ = self._sock.accept()
            except OSError:
                return
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    def _handle(self, conn: socket.socket):
        with conn:
            authed = False
            while True:
                try:
                    request_id, packet_type, body = read_packet(conn)
                except Exception:
                    return
                if packet_type == SERVERDATA_AUTH:
                    authed = body == self.password
                    conn.sendall(encode_packet(request_id, SERVERDATA_RESPONSE_VALUE, ""))
                    conn.sendall(encode_packet(request_id if authed else -1, SERVERDATA_AUTH_RESPONSE, ""))
                    continue
                if not authed:
                    return
                self.commands.append(body)
                reply = self.responses.get(body.split(" ", 1)[0], f"ran {body}")
                if callable(reply):
                    reply = reply(body)
                chunks = [reply[i:i + self.chunk_size] for i in range(0, len(reply), self.chunk_size)] or [""]
                for chunk in chunks:
                    conn.sendall(encode_packet(request_id, SERVERDATA_RESPONSE_VALUE, chunk))


def a2s_info_payload(name="Pisshau", map_name="FFA_Camp", players=2, max_players=8, password=True) -> bytes:
    return (
        b"\xff\xff\xff\xffI\x11"
        + name.encode() + b"\x00"
        + map_name.encode() + b"\x00"
        + b"mordhau\x00Mordhau\x00"
        + struct.pack("<H", 0)
        + bytes([players, max_players, 0, ord("d"), ord("l"), int(password), 0])
    )


class FakeA2SServer:
    """Requires the post-2020 challenge round trip before answering."""

    CHALLENGE = b"\x01\x02\x03\x04"

    def __init__(self, **info):
        self.info = info
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.bind(("127.0.0.1", 0))
        self.port = self._sock.getsockname()[1]
        self._thread = threading.Thread(target=self._serve, daemon=True)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._sock.close()

    def _serve(self):
        while True:
            try:
                data, addr = self._sock.recvfrom(4096)
            except OSError:
                return
            if data.endswith(self.CHALLENGE):
                self._sock.sendto(a2s_info_payload(**self.info), addr)
            else:
                self._sock.sendto(b"\xff\xff\xff\xffA" + self.CHALLENGE, addr)
