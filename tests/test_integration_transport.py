"""Offline tests for the bounded real-stream implementation."""
from __future__ import annotations
import json, os, sys, threading, time, unittest
from pathlib import Path
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
    def test_fragmented_utf8_multiple_frames_and_allowed_notification(self):
        note = json.dumps({"method":"configWarning","params":{"text":"café"}}, ensure_ascii=False).encode()+b"\n"
        response = b'{"id":1,"result":{}}\n{"id":2,"result":{}}\n'
        split = note.index("é".encode()) + 1
        thread = self._write([note[:split], note[split:], response])
        first = self.transport.receive_response(1, time.monotonic()+10); second = self.transport.receive_response(2, time.monotonic()+10)
        thread.join(); self.assertIsInstance(first, SuccessResponse); self.assertIsInstance(second, SuccessResponse)
    def test_outbound_allowlist_and_exact_bytes(self):
        self.transport.send(Request(1,"initialize",{}), time.monotonic()+10)
        self.assertEqual(os.read(self.process.stdin_reader, 100), b'{"id":1,"method":"initialize","params":{}}\n')
        with self.assertRaisesRegex(TransportError,"denied"): self.transport.send(Request(2,"project/create",{}),time.monotonic()+10)
    def test_unknown_notification_server_request_and_string_id_fail_closed(self):
        for payload, message in ((b'{"method":"other"}\n',"notification"),(b'{"id":9,"method":"thing"}\n',"server request"),(b'{"id":"1","result":{}}\n',"correlation")):
            os.write(self.process.stdout_writer,payload)
            with self.assertRaisesRegex(TransportError,message): self.transport.receive_response(1,time.monotonic()+10)
    def test_malformed_utf8_json_envelope_and_incomplete_eof(self):
        for payload, message in ((b'\xff\n',"UTF-8"),(b'{\n',"JSON"),(b'{}\n',"envelope")):
            os.write(self.process.stdout_writer,payload)
            with self.assertRaisesRegex(TransportError,message): self.transport.receive_response(1,time.monotonic()+10)
        os.write(self.process.stdout_writer,b'{'); os.close(self.process.stdout_writer)
        with self.assertRaisesRegex(TransportError,"incomplete"): self.transport.receive_response(1,time.monotonic()+10)

if __name__ == "__main__": unittest.main()
