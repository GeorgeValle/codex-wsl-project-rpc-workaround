"""Offline tests for the bounded real-stream implementation."""
from __future__ import annotations
import json, os, sys, threading, time, unittest
from pathlib import Path
from unittest import mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from codex_wsl_rpc.integration.transport import _StreamTransport, TransportError
from codex_wsl_rpc.protocol import Notification, Request, SuccessResponse

class _Stream:
    def __init__(self, fd): self._fd = fd
    def fileno(self): return self._fd
    def close(self):
        try: os.close(self._fd)
        except OSError: pass

class _Process:
    def __init__(self):
        stdin_r, stdin_w = os.pipe(); stdout_r, stdout_w = os.pipe(); stderr_r, stderr_w = os.pipe()
        self.stdin, self.stdout, self.stderr = _Stream(stdin_w), _Stream(stdout_r), _Stream(stderr_r)
        self.stdin_reader, self.stdout_writer, self.stderr_writer = stdin_r, stdout_w, stderr_w
    def close(self):
        for fd in (self.stdin_reader, self.stdout_writer, self.stderr_writer):
            try: os.close(fd)
            except OSError: pass

class TransportTests(unittest.TestCase):
    def setUp(self): self.process = _Process(); self.transport = _StreamTransport(self.process)
    def tearDown(self): self.transport.close(); self.process.stdin.close(); self.process.stdout.close(); self.process.stderr.close(); self.process.close()
    def _write(self, parts):
        def writer():
            for part in parts: os.write(self.process.stdout_writer, part)
        thread = threading.Thread(target=writer); thread.start(); return thread
    def _send_request(self, request_id, method):
        self.transport.send(Request(request_id, method, {}), time.monotonic()+10)
        os.read(self.process.stdin_reader, 4096)
    def test_fragmented_utf8_multiple_frames_and_allowed_notification(self):
        note = json.dumps({"method":"configWarning","params":{"text":"café"}}, ensure_ascii=False).encode()+b"\n"
        response = b'{"id":1,"result":{}}\n'
        split = note.index("é".encode()) + 1
        self._send_request(1, "initialize")
        thread = self._write([note[:split], note[split:], response])
        first = self.transport.receive_response(1, time.monotonic()+10)
        thread.join()
        self._send_request(2, "project/list")
        os.write(self.process.stdout_writer, b'{"id":2,"result":{}}\n')
        second = self.transport.receive_response(2, time.monotonic()+10)
        self.assertIsInstance(first, SuccessResponse); self.assertIsInstance(second, SuccessResponse)
    def test_outbound_allowlist_and_exact_bytes(self):
        self.transport.send(Request(1,"initialize",{}), time.monotonic()+10)
        self.assertEqual(os.read(self.process.stdin_reader, 100), b'{"id":1,"method":"initialize","params":{}}\n')
        with self.assertRaisesRegex(TransportError,"denied"): self.transport.send(Request(2,"project/create",{}),time.monotonic()+10)
    def test_unknown_notification_server_request_and_mismatched_ids_fail_closed(self):
        self._send_request(1, "initialize")
        for payload, message in ((b'{"method":"other"}\n',"notification"),(b'{"id":9,"method":"thing"}\n',"server request"),(b'{"id":0,"result":{}}\n',"correlation"),(b'{"id":2,"result":{}}\n',"correlation"),(b'{"id":"1","result":{}}\n',"correlation")):
            os.write(self.process.stdout_writer,payload)
            with self.assertRaisesRegex(TransportError,message): self.transport.receive_response(1,time.monotonic()+10)

    def test_string_request_id_requires_exact_string_response(self):
        self._send_request("unpredictable-a", "initialize")
        os.write(self.process.stdout_writer, b'{"id":1,"result":{}}\n')
        with self.assertRaisesRegex(TransportError, "correlation"):
            self.transport.receive_response("unpredictable-a", time.monotonic()+10)

    def test_partial_request_write_poisoned_session_cannot_send_again(self):
        real_write = os.write
        calls = 0
        def partial_then_fail(fd, data):
            nonlocal calls
            calls += 1
            if calls == 1:
                return real_write(fd, bytes(data[:5]))
            raise BrokenPipeError()
        with mock.patch("codex_wsl_rpc.integration.transport.os.write", side_effect=partial_then_fail):
            with self.assertRaisesRegex(TransportError, "broken pipe"):
                self.transport.send(Request("fresh-a", "initialize", {}), time.monotonic()+10)
        with self.assertRaisesRegex(TransportError, "session unusable"):
            self.transport.send(Request("fresh-b", "project/list", {}), time.monotonic()+10)
    def test_malformed_utf8_json_envelope_and_incomplete_eof(self):
        self._send_request(1, "initialize")
        for payload, message in ((b'\xff\n',"UTF-8"),(b'{\n',"JSON"),(b'{}\n',"envelope")):
            os.write(self.process.stdout_writer,payload)
            with self.assertRaisesRegex(TransportError,message): self.transport.receive_response(1,time.monotonic()+10)
        os.write(self.process.stdout_writer,b'{'); os.close(self.process.stdout_writer)
        with self.assertRaisesRegex(TransportError,"incomplete"): self.transport.receive_response(1,time.monotonic()+10)

    def test_future_response_in_same_read_cannot_satisfy_later_request(self):
        self._send_request(1, "initialize")
        os.write(self.process.stdout_writer, b'{"id":1,"result":{}}\n{"id":2,"result":{}}\n')
        self.assertIsInstance(self.transport.receive_response(1, time.monotonic()+10), SuccessResponse)
        with self.assertRaisesRegex(TransportError, "correlation"):
            self._send_request(2, "project/list")

    def test_pipe_buffered_future_response_is_rejected_before_request(self):
        self._send_request(1, "initialize")
        os.write(self.process.stdout_writer, b'{"id":1,"result":{}}\n')
        self.assertIsInstance(self.transport.receive_response(1, time.monotonic()+10), SuccessResponse)
        self.assertFalse(self.transport._buffer)
        os.write(self.process.stdout_writer, b'{"id":2,"result":{}}\n')
        with self.assertRaisesRegex(TransportError, "^response correlation error$"):
            self.transport.send(Request(2, "project/list", {}), time.monotonic()+10)
        self.assertIsNone(self.transport._outstanding_request_id)
        os.set_blocking(self.process.stdin_reader, False)
        with self.assertRaises(BlockingIOError):
            os.read(self.process.stdin_reader, 4096)

    def test_duplicate_response_cannot_survive_until_next_request(self):
        self._send_request(1, "initialize")
        os.write(self.process.stdout_writer, b'{"id":1,"result":{}}\n{"id":1,"result":{}}\n')
        self.assertIsInstance(self.transport.receive_response(1, time.monotonic()+10), SuccessResponse)
        with self.assertRaisesRegex(TransportError, "correlation"):
            self._send_request(2, "project/list")

    def test_prebuffered_stale_future_and_duplicate_responses_fail_closed(self):
        cases = ((1, 1), (3, 2), (1, 2))
        for buffered_id, request_id in cases:
            with self.subTest(buffered_id=buffered_id, request_id=request_id):
                process = _Process()
                transport = _StreamTransport(process)
                try:
                    transport._buffer.extend(json.dumps({"id": buffered_id, "result": {}}).encode() + b"\n")
                    with self.assertRaisesRegex(TransportError, "correlation"):
                        transport.send(Request(request_id, "project/list", {}), time.monotonic()+10)
                finally:
                    transport.close(); process.stdin.close(); process.stdout.close(); process.stderr.close(); process.close()

    def test_allowed_prebuffered_notification_does_not_complete_request(self):
        self.transport._buffer.extend(b'{"method":"configWarning","params":{}}\n')
        self._send_request(2, "project/list")
        os.write(self.process.stdout_writer, b'{"id":2,"result":{}}\n')
        self.assertIsInstance(self.transport.receive_response(2, time.monotonic()+10), SuccessResponse)

    def test_pipe_buffered_notification_is_drained_before_request(self):
        os.write(self.process.stdout_writer, b'{"method":"configWarning","params":{}}\n')
        self._send_request(2, "project/list")
        self.assertEqual(self.transport._notifications, 1)

    def test_pipe_buffered_server_request_and_partial_frame_fail_closed(self):
        for payload, message in ((b'{"id":9,"method":"server/call"}\n', "unexpected server request"),
                                 (b'{"id":2', "preexisting incomplete frame")):
            with self.subTest(message=message):
                process = _Process()
                transport = _StreamTransport(process)
                try:
                    os.write(process.stdout_writer, payload)
                    with self.assertRaisesRegex(TransportError, f"^{message}$"):
                        transport.send(Request(2, "project/list", {}), time.monotonic()+10)
                    self.assertIsNone(transport._outstanding_request_id)
                finally:
                    transport.close(); process.stdin.close(); process.stdout.close(); process.stderr.close(); process.close()

    def test_preexisting_stderr_is_bounded_and_not_a_response(self):
        data = b"private diagnostic"
        os.write(self.process.stderr_writer, data)
        self._send_request(2, "project/list")
        self.assertEqual(self.transport._stderr_total, len(data))
        self.assertEqual(self.transport._stderr, data)
        self.assertEqual(self.transport._outstanding_request_id, 2)

    def test_preflight_no_ready_input_uses_zero_timeout(self):
        original_select = self.transport._selector.select
        calls = []
        def observed_select(timeout=None):
            calls.append(timeout)
            return original_select(timeout)
        self.transport._selector.select = observed_select
        self._send_request(1, "initialize")
        self.assertEqual(calls, [0])

    def test_prebuffered_server_request_and_second_outstanding_request_fail_closed(self):
        self.transport._buffer.extend(b'{"id":9,"method":"server/call"}\n')
        with self.assertRaisesRegex(TransportError, "server request"):
            self._send_request(1, "initialize")
        self.transport._buffer.clear()
        self._send_request(1, "initialize")
        with self.assertRaisesRegex(TransportError, "already outstanding"):
            self.transport.send(Request(2, "project/list", {}), time.monotonic()+10)

    def test_all_json_value_failures_are_malformed_json(self):
        oversized = b'{"id":' + (b'9' * 5000) + b',"result":{}}'
        for frame in (b'{', oversized):
            with self.subTest(size=len(frame)):
                with self.assertRaisesRegex(TransportError, "^malformed JSON$"):
                    self.transport._decode(frame)
        with mock.patch("codex_wsl_rpc.integration.transport.json.loads", side_effect=RecursionError):
            with self.assertRaisesRegex(TransportError, "^malformed JSON$"):
                self.transport._decode(b'[]')

    def test_valid_json_invalid_envelope_remains_distinct(self):
        with self.assertRaisesRegex(TransportError, "^malformed envelope$"):
            self.transport._decode(b'{}')

    def test_deep_valid_json_recursion_is_malformed_envelope(self):
        nested = '[]'
        for _ in range(500):
            nested = '[' + nested + ']'
        frame = ('{"id":1,"result":' + nested + '}').encode()
        with self.assertRaisesRegex(TransportError, "^malformed envelope$"):
            self.transport._decode(frame)

    def test_parse_envelope_recursion_never_escapes(self):
        with mock.patch("codex_wsl_rpc.integration.transport.parse_envelope", side_effect=RecursionError):
            with self.assertRaisesRegex(TransportError, "^malformed envelope$"):
                self.transport._decode(b'{"id":1,"result":{}}')

    def test_valid_nested_envelope_below_recursion_threshold_parses(self):
        nested = []
        for _ in range(20):
            nested = [nested]
        frame = json.dumps({"id": 1, "result": nested}).encode()
        self.assertIsInstance(self.transport._decode(frame), SuccessResponse)

if __name__ == "__main__": unittest.main()
