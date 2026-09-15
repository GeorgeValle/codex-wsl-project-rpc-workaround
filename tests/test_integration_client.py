"""Offline orchestration tests using an injected fake process."""
from __future__ import annotations
import json, os, stat, subprocess, sys, tempfile, threading, unittest
from pathlib import Path
from unittest import mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from codex_wsl_rpc.integration import IntegrationAuthorization, IntegrationError, ReadOnlyProjectListClient
from codex_wsl_rpc.integration.client import (CleanupError, OperatorCancelledError,
    PINNED_CODEX_SHA, UnsupportedPlatformError, _OwnedChildCleanup)
from codex_wsl_rpc.integration.transport import TransportError
from codex_wsl_rpc.protocol import SuccessResponse

class _Stream:
    def __init__(self, fd): self.fd=fd
    def fileno(self): return self.fd
    def close(self):
        try: os.close(self.fd)
        except OSError: pass
class FakeProcess:
    def __init__(self, responses):
        ir, iw=os.pipe(); or_, ow=os.pipe(); er, ew=os.pipe()
        self.stdin,self.stdout,self.stderr=_Stream(iw),_Stream(or_),_Stream(er); self.returncode=0; self.requests=[]
        os.close(ew)
        def server():
            source=os.fdopen(ir,"rb",buffering=0); sink=os.fdopen(ow,"wb",buffering=0)
            response_index=0
            while response_index < len(responses):
                request=json.loads(source.readline()); self.requests.append(request)
                if "id" in request:
                    sink.write(json.dumps(responses[response_index]).encode()+b"\n")
                    response_index += 1
            source.close(); sink.close()
        self.thread=threading.Thread(target=server); self.thread.start()
    def wait(self,timeout): self.thread.join(timeout); return 0
    def terminate(self): pass
    def kill(self): pass

class CleanupProcess:
    def __init__(self, waits):
        self.stdin=mock.Mock(); self.returncode=None; self.waits=iter(waits)
        self.terminate=mock.Mock(); self.kill=mock.Mock()
    def wait(self, timeout):
        result=next(self.waits)
        if isinstance(result, BaseException): raise result
        self.returncode=result
        return result

class ScriptedTransport:
    def __init__(self, failure_at): self.failure_at=failure_at; self.step=0
    def _advance(self):
        self.step += 1
        if self.step == self.failure_at: raise TransportError("/private/path secret project data")
    def send(self, message, deadline): self._advance()
    def receive_response(self, request_id, deadline):
        self._advance()
        if request_id == 1:
            return SuccessResponse(1, {"userAgent":"private", "codexHome":"/private", "platformFamily":"unix", "platformOs":"linux"})
    def close(self): pass

def project(name="secret", roots=None):
    return {"id":"private-id","name":name,"roots":roots or [],"metadata":{"secret":"value"},"position":1,"createdAt":2,"updatedAt":3,"recencyAt":None}

class ClientTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); root=Path(self.temp.name); self.exe=root/"codex-native"; self.exe.write_bytes(b"\x7fELFfake"); self.exe.chmod(stat.S_IRUSR|stat.S_IWUSR|stat.S_IXUSR); self.home=root/"home"; self.home.mkdir()
    def tearDown(self): self.temp.cleanup()
    def _client(self, **kwargs):
        proc_reader=kwargs.pop("_proc_reader", lambda path: "5.15.90.1-MICROSOFT-standard-WSL2")
        return ReadOnlyProjectListClient(
            executable_path=self.exe, home_path=self.home,
            authorization=IntegrationAuthorization.READ_ONLY_PROJECT_LIST,
            _proc_reader=proc_reader,
            **kwargs,
        )
    def _run(self,data,next_cursor=None,codex_home="/private"):
        fake=FakeProcess([{"id":1,"result":{"userAgent":"private","codexHome":codex_home,"platformFamily":"unix","platformOs":"linux"}}, {"id":2,"result":{"data":data,"nextCursor":next_cursor}}])
        client=self._client(_popen=lambda *a,**k: fake)
        return client.list_one_page(),fake
    def test_success_exact_sequence_and_safe_summary(self):
        result,fake=self._run([project(roots=[{"path":"/home/person/private"}])],"raw-cursor")
        self.assertEqual([r.get("method") for r in fake.requests],["initialize","initialized","project/list"])
        self.assertEqual([r.get("id") for r in fake.requests],[1,None,2]); self.assertTrue(fake.requests[0]["params"]["capabilities"]["experimentalApi"])
        self.assertEqual(fake.requests[2]["params"],{"cursor":None,"limit":25,"sortKey":"position","sortDirection":"asc"})
        safe=json.dumps(result.summary.to_safe_dict()); self.assertNotIn("secret",safe); self.assertNotIn("private-id",safe); self.assertNotIn("raw-cursor",safe)
        self.assertNotIn(str(self.exe), safe); self.assertNotIn(str(self.home), safe)
        self.assertEqual(result.summary.returned_page_count,1); self.assertTrue(result.summary.has_more)
        summary=result.summary.to_safe_dict()
        self.assertEqual(summary["protocol_reference_sha"], PINNED_CODEX_SHA)
        self.assertEqual(summary["target_provenance"], "operator_confirmed_openai_codex_unverified_by_repository")
        self.assertEqual(summary["target_revision_mapping"], "NOT_ESTABLISHED")
        self.assertEqual(summary["target_version"], "unobserved")
        self.assertNotIn("tested_sha", summary); self.assertNotIn("version", summary)
        self.assertIn("unverified", summary["target_provenance"])
        self.assertIn("validates only its executable form", IntegrationAuthorization.READ_ONLY_PROJECT_LIST.value)
        self.assertEqual(summary["codex_home_category"], "posix_absolute")
        self.assertNotIn("codex_home", summary)

    def test_codex_home_category_is_derived_without_exposing_raw_path(self):
        cases = (
            ("/home/user/.codex", "posix_absolute"),
            (r"C:\Users\User\.codex", "windows_drive_absolute"),
            ("C:/Users/User/.codex", "windows_drive_absolute"),
            (r"\\server\share\codex", "unc_absolute"),
            ("relative/path", "relative"),
            ("./codex", "relative"),
            ("", "empty"),
        )
        for codex_home, expected in cases:
            with self.subTest(codex_home=codex_home, expected=expected):
                result, _ = self._run([], codex_home=codex_home)
                safe = result.summary.to_safe_dict()
                self.assertEqual(safe["codex_home_category"], expected)
                self.assertNotIn("codex_home", safe)
                if codex_home:
                    self.assertNotIn(codex_home, json.dumps(safe))

    def test_personal_codex_home_is_not_exposed_by_safe_summary(self):
        personal_path = "/home/PersonalUser/private-codex-state"
        result, _ = self._run([], codex_home=personal_path)
        safe = json.dumps(result.summary.to_safe_dict())
        self.assertEqual(result.summary.codex_home_category, "posix_absolute")
        self.assertNotIn(personal_path, safe)
        self.assertNotIn("PersonalUser", safe)
    def test_empty_page(self):
        result,_=self._run([]); self.assertEqual(result.summary.returned_page_count,0); self.assertFalse(result.summary.has_more)

    def test_cleanup_tracks_graceful_terminate_and_kill(self):
        cases=(
            ([0], "graceful", 0, 0),
            ([subprocess.TimeoutExpired("fake", 1), 0], "terminated_owned_child", 1, 0),
            ([subprocess.TimeoutExpired("fake", 1), subprocess.TimeoutExpired("fake", 1), 0], "killed_owned_child", 1, 1),
        )
        for waits, expected, terminates, kills in cases:
            with self.subTest(expected=expected):
                process=CleanupProcess(waits)
                state = _OwnedChildCleanup(process, None)
                self.assertEqual(ReadOnlyProjectListClient._cleanup(state), expected)
                self.assertTrue(state.completed)
                self.assertEqual(process.terminate.call_count, terminates)
                self.assertEqual(process.kill.call_count, kills)

    def test_cleanup_raises_when_owned_child_cannot_be_reaped(self):
        process=CleanupProcess([subprocess.TimeoutExpired("fake", 1)] * 3)
        with self.assertRaisesRegex(IntegrationError, "owned-child cleanup failed"):
            ReadOnlyProjectListClient._cleanup(_OwnedChildCleanup(process, None))
        process.terminate.assert_called_once_with(); process.kill.assert_called_once_with()

    def test_summary_reports_actual_forced_cleanup(self):
        fake=FakeProcess([{"id":1,"result":{"userAgent":"private","codexHome":"/private","platformFamily":"unix","platformOs":"linux"}}, {"id":2,"result":{"data":[],"nextCursor":None}}])
        original_wait=fake.wait; calls=0
        def wait(timeout):
            nonlocal calls
            calls += 1
            if calls == 1: raise subprocess.TimeoutExpired("fake", timeout)
            return original_wait(timeout)
        fake.wait=wait
        client=self._client(_popen=lambda *a,**k: fake)
        self.assertEqual(client.list_one_page().summary.cleanup_outcome, "terminated_owned_child")

    def test_explicit_cleanup_failure_is_not_retried_or_masked(self):
        fake=FakeProcess([{"id":1,"result":{"userAgent":"private","codexHome":"/private","platformFamily":"unix","platformOs":"linux"}}, {"id":2,"result":{"data":[],"nextCursor":None}}])
        client=self._client(_popen=lambda *a,**k: fake)
        primary=CleanupError("owned-child cleanup failed")
        def fail_cleanup(state):
            state.started = True
            raise primary
        with mock.patch.object(client, "_cleanup", side_effect=fail_cleanup) as cleanup:
            with self.assertRaises(CleanupError) as caught: client.list_one_page()
        self.assertIs(caught.exception, primary); cleanup.assert_called_once()

    def test_early_failures_and_interrupts_receive_one_cleanup_attempt(self):
        for failure in (TransportError("private"), KeyboardInterrupt()):
            with self.subTest(failure=type(failure).__name__):
                process=CleanupProcess([0]); transport=mock.Mock()
                transport.send.side_effect=failure
                client=self._client(_popen=lambda *a,**k: process)
                with mock.patch("codex_wsl_rpc.integration.client._StreamTransport", return_value=transport), mock.patch.object(client, "_cleanup", wraps=client._cleanup) as cleanup:
                    with self.assertRaises(IntegrationError): client.list_one_page()
                cleanup.assert_called_once()
                state = cleanup.call_args.args[0]
                self.assertTrue(state.completed)
                self.assertIsNone(state.process)

    def test_interrupted_cleanup_retains_ownership_and_never_repeats_signals(self):
        cases = (
            ([KeyboardInterrupt(), 0], 0, 0),
            ([subprocess.TimeoutExpired("fake", 1), KeyboardInterrupt(), 0], 1, 0),
            ([subprocess.TimeoutExpired("fake", 1), subprocess.TimeoutExpired("fake", 1), KeyboardInterrupt(), 0], 1, 1),
        )
        for waits, terminates, kills in cases:
            with self.subTest(terminates=terminates, kills=kills):
                process = CleanupProcess(waits)
                state = _OwnedChildCleanup(process, None)
                with self.assertRaises(OperatorCancelledError):
                    ReadOnlyProjectListClient._cleanup(state)
                self.assertTrue(state.started)
                self.assertTrue(state.completed)
                self.assertIsNone(state.process)
                self.assertEqual(process.terminate.call_count, terminates)
                self.assertEqual(process.kill.call_count, kills)

    def test_cleanup_error_wins_over_interruption_without_second_attempt(self):
        process = CleanupProcess([
            subprocess.TimeoutExpired("fake", 1),
            subprocess.TimeoutExpired("fake", 1),
            KeyboardInterrupt(),
            subprocess.TimeoutExpired("fake", 1),
        ])
        state = _OwnedChildCleanup(process, None)
        with self.assertRaises(CleanupError):
            ReadOnlyProjectListClient._cleanup(state)
        self.assertTrue(state.started)
        self.assertFalse(state.completed)
        process.terminate.assert_called_once_with()
        process.kill.assert_called_once_with()

    def test_method_not_found_remains_ambiguous_and_private(self):
        fake=FakeProcess([{"id":1,"result":{"userAgent":"private","codexHome":"/private","platformFamily":"unix","platformOs":"linux"}}, {"id":2,"error":{"code":-32601,"message":"secret method or store detail","data":{"path":"/private/project"}}}])
        client=self._client(_popen=lambda *a,**k: fake)
        with self.assertRaises(IntegrationError) as caught: client.list_one_page()
        self.assertEqual(str(caught.exception), "project/list unavailable or unsupported")
        self.assertNotIn("store unavailable", str(caught.exception)); self.assertNotIn("secret", str(caught.exception)); self.assertNotIn("private", str(caught.exception))

    def test_other_protocol_errors_remain_generic_and_private(self):
        fake=FakeProcess([{"id":1,"result":{"userAgent":"private","codexHome":"/private","platformFamily":"unix","platformOs":"linux"}}, {"id":2,"error":{"code":-32603,"message":"secret","data":{"project":"private"}}}])
        client=self._client(_popen=lambda *a,**k: fake)
        with self.assertRaises(IntegrationError) as caught: client.list_one_page()
        self.assertEqual(str(caught.exception), "project/list protocol error")

    def test_transport_failures_use_explicit_safe_phase(self):
        expected={1:"initialize", 2:"initialize", 3:"initialize", 4:"project/list", 5:"project/list"}
        for failure_at, category in expected.items():
            with self.subTest(failure_at=failure_at):
                process=CleanupProcess([0])
                transport=ScriptedTransport(failure_at)
                with mock.patch("codex_wsl_rpc.integration.client._StreamTransport", return_value=transport):
                    client=self._client(_popen=lambda *a,**k: process)
                    with self.assertRaises(IntegrationError) as caught: client.list_one_page()
                rendered=str(caught.exception)
                self.assertEqual(rendered, f"{category} transport failure")
                self.assertEqual(caught.exception.category, f"{category.replace('/', '_')}_transport_failure")
                self.assertNotIn("private", rendered); self.assertNotIn("secret", rendered)

    def test_platform_validation_requires_positive_proc_wsl_evidence_first(self):
        accepted = ("4.4.0-19041-Microsoft", "5.15.90.1-mIcRoSoFt-standard-WSL2", "Linux WSL kernel")
        for evidence in accepted:
            with self.subTest(evidence=evidence):
                client=self._client(_proc_reader=lambda path, text=evidence: text)
                self.assertTrue(client._is_wsl())
        rejected = (("linux", "6.8.0-generic"), ("linux", "container-linux"),
                    ("win32", "Microsoft WSL2"), ("darwin", "Microsoft WSL2"))
        for platform, evidence in rejected:
            with self.subTest(platform=platform, evidence=evidence):
                popen=mock.Mock()
                client=self._client(_platform=platform, _proc_reader=lambda path, text=evidence: text,
                                    _popen=popen)
                with self.assertRaises(UnsupportedPlatformError): client.list_one_page()
                popen.assert_not_called()

    def test_missing_proc_evidence_and_environment_alone_fail_before_target_access(self):
        missing=self.temp.name + "/does-not-exist"
        popen=mock.Mock()
        client=ReadOnlyProjectListClient(
            executable_path=Path(missing), home_path=self.home,
            authorization=IntegrationAuthorization.READ_ONLY_PROJECT_LIST,
            _popen=popen, _platform="linux",
            _proc_reader=lambda path: (_ for _ in ()).throw(OSError("unreadable")),
        )
        with mock.patch.dict(os.environ, {"WSL_DISTRO_NAME":"Ubuntu", "WSL_INTEROP":"fake"}):
            with self.assertRaises(UnsupportedPlatformError): client.list_one_page()
        popen.assert_not_called()

if __name__ == "__main__": unittest.main()
