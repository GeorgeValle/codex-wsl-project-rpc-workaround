"""A deliberately non-streaming, in-memory JSON-line boundary."""

from __future__ import annotations

import json

from codex_wsl_rpc.protocol import Notification, ProtocolDecodeError, Request, parse_envelope

from .server import FakeAppServer


class InMemoryTransport:
    """Pass exactly one complete JSON line to a fake server synchronously."""

    def __init__(self, server: FakeAppServer) -> None:
        if not isinstance(server, FakeAppServer):
            raise TypeError("server must be a FakeAppServer")
        self._server = server

    def send(self, line: str) -> str | None:
        if not isinstance(line, str):
            raise ProtocolDecodeError("frame: expected text")
        if not line.endswith("\n") or "\n" in line[:-1] or "\r" in line[:-1]:
            raise ProtocolDecodeError("frame: expected exactly one newline-terminated JSON value")
        try:
            value = json.loads(line[:-1])
        except (json.JSONDecodeError, UnicodeError) as error:
            raise ProtocolDecodeError("frame: invalid JSON") from error
        envelope = parse_envelope(value)
        if not isinstance(envelope, (Request, Notification)):
            raise ProtocolDecodeError("frame: expected client request or notification")
        response = self._server.handle(envelope)
        if response is None:
            return None
        return json.dumps(response.to_wire()) + "\n"
