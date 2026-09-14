from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from codex_wsl_rpc.mock import FakeAppServer  # noqa: E402
from codex_wsl_rpc.protocol import ErrorResponse, Notification, Request, SuccessResponse  # noqa: E402


def initialize(server, request_id=1, capabilities=None, name="tests"):
    params={"clientInfo":{"name":name,"version":"1"}}
    if capabilities is not None: params["capabilities"]={"experimentalApi":capabilities}
    return server.handle(Request(request_id,"initialize",params))


class ServerTests(unittest.TestCase):
    def test_initialize_once_and_deterministic_response(self):
        server=FakeAppServer(); response=initialize(server)
        self.assertIsInstance(response,SuccessResponse)
        self.assertEqual(response.result,{"userAgent":"codex-wsl-rpc-mock/1","codexHome":"/mock/codex-home","platformFamily":"mock","platformOs":"mock"})
        duplicate=initialize(server,2); self.assertEqual((duplicate.error.code,duplicate.error.message),(-32600,"Already initialized"))

    def test_valid_header_client_names_initialize(self):
        for name in ("tests-client", "tests\tclient"):
            with self.subTest(name=repr(name)):
                server=FakeAppServer()
                self.assertIsInstance(initialize(server,name=name),SuccessResponse)

    def test_malformed_initialize_does_not_transition(self):
        server=FakeAppServer(); bad=server.handle(Request(1,"initialize",{}))
        self.assertEqual(bad.error.code,-32602); self.assertIsInstance(initialize(server,2),SuccessResponse)

    def test_invalid_header_client_names_do_not_initialize(self):
        for name in ("line\nfeed","carriage\rreturn","control\x01value","control\x1fvalue","delete\x7fvalue","non-ascii-\N{SNOWMAN}"):
            with self.subTest(name=repr(name)):
                server=FakeAppServer()
                invalid=initialize(server,capabilities=True,name=name)
                self.assertEqual(
                    (invalid.error.code,invalid.error.message),
                    (-32600,f"Invalid clientInfo.name: '{name}'. Must be a valid HTTP header value."),
                )
                denied=server.handle(Request(2,"project/list",{}))
                self.assertEqual((denied.error.code,denied.error.message),(-32600,"Not initialized"))
                self.assertIsInstance(initialize(server,3,capabilities=True),SuccessResponse)
                self.assertIsInstance(server.handle(Request(4,"project/list",{})),SuccessResponse)
                duplicate=initialize(server,5)
                self.assertEqual((duplicate.error.code,duplicate.error.message),(-32600,"Already initialized"))

    def test_lifecycle_and_initialized_notification(self):
        server=FakeAppServer()
        self.assertIsNone(server.handle(Notification("initialized")))
        denied=server.handle(Request(1,"project/list",{})); self.assertEqual((denied.error.code,denied.error.message),(-32600,"Not initialized"))
        initialize(server); self.assertIsNone(server.handle(Notification("initialized")))

    def test_capability_cases(self):
        for capability in (None,False):
            server=FakeAppServer(); initialize(server,capabilities=capability)
            response=server.handle(Request(2,"project/list",{})); self.assertEqual(response.error.code,-32600)
        server=FakeAppServer(); initialize(server,capabilities=True)
        self.assertIsInstance(server.handle(Request(2,"project/list",{})),SuccessResponse)

    def test_unknown_and_mutations_are_not_dispatched(self):
        methods=("unknown","project/read","project/create","project/update","project/import","project/move","project/delete")
        for method in methods:
            server=FakeAppServer(); initialize(server)
            response=server.handle(Request(2,method,{}))
            self.assertEqual((response.error.code,response.error.message),(-32601,"Method not found"))

    def test_internal_error_is_safe(self):
        class BrokenStore:
            def snapshot(self): raise RuntimeError("secret /private/path 0x123")
        server=FakeAppServer(); initialize(server,capabilities=True); server._store=BrokenStore()
        response=server.handle(Request(2,"project/list",{}))
        self.assertEqual((response.error.code,response.error.message),(-32603,"Internal mock server error"))
        self.assertNotIn("secret",response.error.message)

if __name__ == "__main__": unittest.main()
