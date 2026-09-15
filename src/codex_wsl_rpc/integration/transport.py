"""Bounded nonblocking JSON-lines transport for one owned child process."""

from __future__ import annotations

import codecs
import json
import os
import selectors
import time
from typing import Callable

from codex_wsl_rpc.protocol import Envelope, Notification, Request, parse_envelope

MAX_STDOUT_FRAME = 1024 * 1024
MAX_STDOUT_SESSION = 8 * 1024 * 1024
MAX_STDERR_RETAINED = 32 * 1024
MAX_STDERR_TOTAL = 1024 * 1024
MAX_NOTIFICATIONS = 32
MAX_NOTIFICATION_BYTES = 1024 * 1024
ALLOWED_WRITES = frozenset({"initialize", "initialized", "project/list"})
ALLOWED_NOTIFICATIONS = frozenset({"configWarning", "remoteControl/status/changed"})


class TransportError(RuntimeError):
    """A safe, categorized stream failure."""


class _StreamTransport:
    def __init__(self, process, *, clock: Callable[[], float] = time.monotonic,
                 selector_factory=selectors.DefaultSelector) -> None:
        self._process = process
        self._clock = clock
        self._selector = selector_factory()
        self._buffer = bytearray()
        self._stdout_total = 0
        self._stderr_total = 0
        self._stderr = bytearray()
        self._notifications = 0
        self._notification_bytes = 0
        for stream, event in ((process.stdout, "stdout"), (process.stderr, "stderr")):
            os.set_blocking(stream.fileno(), False)
            self._selector.register(stream, selectors.EVENT_READ, event)
        os.set_blocking(process.stdin.fileno(), False)

    def close(self) -> None:
        self._selector.close()

    def send(self, envelope: Request | Notification, deadline: float) -> None:
        if envelope.method not in ALLOWED_WRITES:
            raise TransportError("outbound method denied")
        if isinstance(envelope, Request):
            allowed = envelope.method in {"initialize", "project/list"}
        else:
            allowed = envelope.method == "initialized" and envelope.params is None
        if not allowed:
            raise TransportError("outbound envelope denied")
        payload = json.dumps(envelope.to_wire(), separators=(",", ":"), ensure_ascii=False).encode("utf-8") + b"\n"
        view = memoryview(payload)
        while view:
            if self._clock() >= deadline:
                raise TransportError("write timeout")
            try:
                written = os.write(self._process.stdin.fileno(), view)
            except BlockingIOError:
                written = 0
            except BrokenPipeError as error:
                raise TransportError("broken pipe") from error
            if written:
                view = view[written:]
                continue
            with selectors.DefaultSelector() as selector:
                selector.register(self._process.stdin, selectors.EVENT_WRITE)
                selector.select(max(0.0, deadline - self._clock()))

    def receive_response(self, expected_id: int, deadline: float) -> Envelope:
        while True:
            frame = self._take_frame()
            if frame is not None:
                envelope = self._decode(frame)
                if isinstance(envelope, Notification):
                    self._accept_notification(envelope, len(frame))
                    continue
                if isinstance(envelope, Request):
                    raise TransportError("unexpected server request")
                if type(envelope.id) is not int or envelope.id != expected_id:
                    raise TransportError("response correlation error")
                return envelope
            remaining = deadline - self._clock()
            if remaining <= 0:
                raise TransportError("response timeout")
            events = self._selector.select(remaining)
            if not events:
                raise TransportError("response timeout")
            for key, _ in events:
                try:
                    chunk = os.read(key.fileobj.fileno(), 65536)
                except BlockingIOError:
                    continue
                if key.data == "stderr":
                    if not chunk:
                        self._selector.unregister(key.fileobj)
                        continue
                    self._stderr_total += len(chunk)
                    if self._stderr_total > MAX_STDERR_TOTAL:
                        raise TransportError("stderr resource limit")
                    room = MAX_STDERR_RETAINED - len(self._stderr)
                    self._stderr.extend(chunk[:max(0, room)])
                elif not chunk:
                    if self._buffer:
                        raise TransportError("EOF with incomplete frame")
                    raise TransportError("early EOF")
                else:
                    self._stdout_total += len(chunk)
                    if self._stdout_total > MAX_STDOUT_SESSION:
                        raise TransportError("stdout session limit")
                    self._buffer.extend(chunk)
                    if b"\n" not in self._buffer and len(self._buffer) > MAX_STDOUT_FRAME:
                        raise TransportError("stdout frame limit")

    def _take_frame(self) -> bytes | None:
        newline = self._buffer.find(b"\n")
        if newline < 0:
            return None
        if newline > MAX_STDOUT_FRAME:
            raise TransportError("stdout frame limit")
        frame = bytes(self._buffer[:newline])
        del self._buffer[:newline + 1]
        return frame

    @staticmethod
    def _decode(frame: bytes) -> Envelope:
        try:
            text = codecs.decode(frame, "utf-8", "strict")
        except UnicodeDecodeError as error:
            raise TransportError("malformed UTF-8") from error
        try:
            value = json.loads(text)
        except (ValueError, RecursionError) as error:
            raise TransportError("malformed JSON") from error
        try:
            return parse_envelope(value)
        except (ValueError, TypeError) as error:
            raise TransportError("malformed envelope") from error

    def _accept_notification(self, notification: Notification, size: int) -> None:
        if notification.method not in ALLOWED_NOTIFICATIONS:
            raise TransportError("unexpected notification")
        self._notifications += 1
        self._notification_bytes += size
        if self._notifications > MAX_NOTIFICATIONS or self._notification_bytes > MAX_NOTIFICATION_BYTES:
            raise TransportError("notification resource limit")
