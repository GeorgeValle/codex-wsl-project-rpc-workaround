import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from codex_wsl_rpc.mock import FakeAppServer, InMemoryTransport, MockClient, MockServerError  # noqa: E402
from codex_wsl_rpc.protocol import ClientInfo, InitializeCapabilities, InitializeResponse, ProjectListResponse  # noqa: E402


class RecordingTransport(InMemoryTransport):
    def __init__(self, server): super().__init__(server); self.lines=[]
    def send(self,line): self.lines.append(line); return super().send(line)


class ClientTests(unittest.TestCase):
    def test_happy_path_typed_and_ids(self):
        transport=RecordingTransport(FakeAppServer()); client=MockClient(transport)
        initialized=client.initialize(ClientInfo("tests","1"),InitializeCapabilities(True)); client.send_initialized(); projects=client.list_projects()
        self.assertIsInstance(initialized,InitializeResponse); self.assertIsInstance(projects,ProjectListResponse)
        self.assertEqual([json.loads(line).get("id") for line in transport.lines],[1,None,2])

    def test_server_errors_carry_protocol_error(self):
        client=MockClient(InMemoryTransport(FakeAppServer()))
        with self.assertRaises(MockServerError) as caught: client.list_projects()
        self.assertEqual(caught.exception.error.code,-32600)
        client.initialize(ClientInfo("tests","1"))
        with self.assertRaises(MockServerError): client.list_projects()
        with self.assertRaises(MockServerError): client.initialize(ClientInfo("tests","1"))

    def test_no_auto_initialize_or_capability_or_retry(self):
        transport=RecordingTransport(FakeAppServer()); client=MockClient(transport)
        with self.assertRaises(MockServerError): client.list_projects()
        self.assertEqual(len(transport.lines),1)

    def test_response_id_mismatch(self):
        class MismatchTransport(InMemoryTransport):
            def send(self,line): return '{"id":999,"result":{}}\n'
        with self.assertRaisesRegex(RuntimeError,"id mismatch"):
            MockClient(MismatchTransport(FakeAppServer())).list_projects()

if __name__ == "__main__": unittest.main()
