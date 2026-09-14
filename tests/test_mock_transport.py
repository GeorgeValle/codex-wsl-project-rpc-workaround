import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from codex_wsl_rpc.mock import FakeAppServer, InMemoryTransport  # noqa: E402
from codex_wsl_rpc.protocol import ProtocolDecodeError  # noqa: E402


class TransportTests(unittest.TestCase):
    def setUp(self): self.transport = InMemoryTransport(FakeAppServer())

    def test_request_ids_and_exact_frame(self):
        for request_id in (7, "seven"):
            response = self.transport.send(json.dumps({"id": request_id, "method": "project/list"}) + "\n")
            self.assertEqual(json.loads(response)["id"], request_id)

    def test_notification_returns_none(self):
        self.assertIsNone(self.transport.send('{"method": "initialized"}\n'))

    def test_bad_framing(self):
        for value in ('{"method":"initialized"}', '{}\n{}\n', '{}\r\n', '{}\n '):
            with self.subTest(value=value), self.assertRaises(ProtocolDecodeError): self.transport.send(value)

    def test_decode_failures(self):
        for value in ('not json\n', '[]\n', '{"id":1,"result":{}}\n'):
            with self.subTest(value=value), self.assertRaises(ProtocolDecodeError): self.transport.send(value)

    def test_response_isolation(self):
        line=json.dumps({"id":1,"method":"initialize","params":{"clientInfo":{"name":"n","version":"1"},"extra":[]}})+"\n"
        response=self.transport.send(line); decoded=json.loads(response); decoded["result"]["codexHome"]="changed"
        self.assertEqual(json.loads(response)["result"]["codexHome"], "/mock/codex-home")

if __name__ == "__main__": unittest.main()
