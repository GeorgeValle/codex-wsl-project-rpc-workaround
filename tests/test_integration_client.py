"""Offline orchestration tests using an injected fake process."""
from __future__ import annotations
import json, os, signal, stat, subprocess, sys, tempfile, threading, unittest
from pathlib import Path
from unittest import mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from codex_wsl_rpc.integration import IntegrationAuthorization, IntegrationError, ReadOnlyProjectListClient
from codex_wsl_rpc.integration.client import (CleanupError, InvalidTargetError,
    OperatorCancelledError, PINNED_CODEX_SHA, StartupError,
    UnsupportedPlatformError, UnsupportedTargetError, _OwnedChildCleanup,
    _SignalDelivery, _is_wsl_kernel_release)
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
                    response = dict(responses[response_index])
                    response["id"] = request["id"]
                    sink.write(json.dumps(response).encode()+b"\n")
                    response_index += 1
            source.close(); sink.close()
        self.thread=threading.Thread(target=server); self.thread.start()
    def wait(self,timeout): self.thread.join(timeout); return 0
    def poll(self):
        if self.thread.is_alive(): return None
        self.returncode = 0
        return 0
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

class FakeClock:
    def __init__(self): self.now = 0.0
    def __call__(self): return self.now

class ScriptedClock:
    def __init__(self, values): self.values = iter(values); self.last = 0.0
    def __call__(self):
        value = next(self.values, self.last)
        if isinstance(value, BaseException): raise value
        self.last = value
        return value

class TimedCleanupProcess(CleanupProcess):
    def __init__(self, clock, waits):
        super().__init__([]); self.clock=clock; self.waits=iter(waits); self.timeouts=[]
    def wait(self, timeout):
        self.timeouts.append(timeout)
        result, elapsed = next(self.waits)
        self.clock.now += elapsed
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
        if self.step <= 2:
            return SuccessResponse(request_id, {"userAgent":"private", "codexHome":"/private", "platformFamily":"unix", "platformOs":"linux"})
        return SuccessResponse(request_id, {"data": [], "nextCursor": None})
    def close(self): pass

class TerminalCleanupTransport:
    _supports_terminal_drain = True

    def __init__(self, states):
        self.states = iter(states)
        self.terminal_error = None
        self.closed = False

    def drain_terminal(self, process, deadline):
        return next(self.states)

    def close(self):
        self.closed = True

def project(name="secret", roots=None):
    return {"id":"private-id","name":name,"roots":roots or [],"metadata":{"secret":"value"},"position":1,"createdAt":2,"updatedAt":3,"recencyAt":None}

class ClientTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); root=Path(self.temp.name); self.exe=root/"codex-native"; self.exe.write_bytes(b"\x7fELFfake"); self.exe.chmod(stat.S_IRUSR|stat.S_IWUSR|stat.S_IXUSR); self.home=root/"home"; self.home.mkdir()
    def tearDown(self): self.temp.cleanup()
    def _client(self, **kwargs):
        proc_reader=kwargs.pop("_proc_reader", lambda path: "5.15.90.1-MICROSOFT-standard-WSL2")
        request_ids = iter(("init-test-id", "list-test-id"))
        id_generator = kwargs.pop("_id_generator", lambda: next(request_ids))
        return ReadOnlyProjectListClient(
            executable_path=self.exe, home_path=self.home,
            authorization=IntegrationAuthorization.READ_ONLY_PROJECT_LIST,
            _proc_reader=proc_reader,
            _id_generator=id_generator,
            **kwargs,
        )
    def _run(self,data,next_cursor=None,codex_home="/private",
             platform_family="unix", platform_os="linux"):
        fake=FakeProcess([{"id":1,"result":{"userAgent":"private","codexHome":codex_home,"platformFamily":platform_family,"platformOs":platform_os}}, {"id":2,"result":{"data":data,"nextCursor":next_cursor}}])
        client=self._client(_popen=lambda *a,**k: fake)
        return client.list_one_page(),fake
    def test_success_exact_sequence_and_safe_summary(self):
        result,fake=self._run([project(roots=[{"path":"/home/person/private"}])],"raw-cursor")
        self.assertEqual([r.get("method") for r in fake.requests],["initialize","initialized","project/list"])
        self.assertEqual([r.get("id") for r in fake.requests],["init-test-id",None,"list-test-id"]); self.assertTrue(fake.requests[0]["params"]["capabilities"]["experimentalApi"])
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
        for field in ("product_state_impact", "network_effects", "helper_process_effects"):
            self.assertEqual(summary[field], "NOT_ESTABLISHED")
        self.assertFalse(summary["direct_state_inspection"])
        self.assertFalse(summary["mutation_attempted"])

    def test_request_ids_are_distinct_injected_unpredictable_strings(self):
        result, fake = self._run([])
        ids = [request["id"] for request in fake.requests if "id" in request]
        self.assertEqual(ids, ["init-test-id", "list-test-id"])
        self.assertEqual(len(set(ids)), 2)
        self.assertTrue(all(isinstance(request_id, str) for request_id in ids))
        self.assertIsNotNone(result.summary)

    def test_spawn_handoff_defers_pending_interrupt_until_child_is_owned(self):
        fake = CleanupProcess([0])
        masks = []
        def sigmask(operation, signals):
            masks.append((operation, signals))
            if operation == signal.SIG_SETMASK:
                raise KeyboardInterrupt()
            return frozenset()
        client = self._client(_popen=lambda *a, **k: fake, _sigmask=sigmask)
        with self.assertRaises(OperatorCancelledError):
            client.list_one_page()
        fake.stdin.close.assert_called_once_with()
        self.assertEqual([operation for operation, _ in masks],
                         [signal.SIG_BLOCK, signal.SIG_SETMASK,
                          signal.SIG_BLOCK, signal.SIG_SETMASK])

    def test_platform_values_are_reduced_to_safe_reviewed_categories(self):
        cases = (
            ("unix", "linux", "unix", "linux"),
            ("windows", "windows", "windows", "windows"),
            ("", "", "unknown", "unknown"),
            ("macos", "macos", "unknown", "unknown"),
            ("/home/person/private", "secret-token", "unknown", "unknown"),
            ("linux\n/private/diagnostic", "windows\x00secret", "unknown", "unknown"),
        )
        for family, os_name, expected_family, expected_os in cases:
            with self.subTest(family=family, os_name=os_name):
                result, _ = self._run([], platform_family=family, platform_os=os_name)
                safe = result.summary.to_safe_dict()
                self.assertEqual(safe["platform_family"], expected_family)
                self.assertEqual(safe["platform_os"], expected_os)
                rendered = json.dumps(safe)
                if expected_family == "unknown" and family:
                    self.assertNotIn(family, rendered)
                if expected_os == "unknown" and os_name:
                    self.assertNotIn(os_name, rendered)

    def test_descriptor_backed_launch_executes_retained_validated_object(self):
        observed = {}
        fake = FakeProcess([{"id": 1, "result": {"userAgent": "private", "codexHome": "/private", "platformFamily": "unix", "platformOs": "linux"}},
                            {"id": 2, "result": {"data": [], "nextCursor": None}}])
        def popen(argv, **kwargs):
            replacement = self.exe.with_suffix(".new")
            replacement.write_bytes(b"replacement")
            os.replace(replacement, self.exe)
            observed["bytes"] = Path(argv[0]).read_bytes()
            observed["argv"] = argv
            observed["pass_fds"] = kwargs["pass_fds"]
            return fake
        result = self._client(_popen=popen).list_one_page()
        self.assertEqual(observed["bytes"], b"\x7fELFfake")
        self.assertRegex(observed["argv"][0], r"^/proc/self/fd/\d+$")
        self.assertEqual(len(observed["pass_fds"]), 2)
        self.assertEqual(observed["argv"][0], f"/proc/self/fd/{observed['pass_fds'][0]}")
        self.assertRegex(fake.requests[0].get("method", ""), "initialize")
        for inherited_fd in observed["pass_fds"]:
            with self.assertRaises(OSError): os.fstat(inherited_fd)
        self.assertEqual(result.summary.target_revision_mapping, "NOT_ESTABLISHED")

    def test_home_uses_retained_directory_identity_after_rename_and_recreate(self):
        observed = {}
        fake = FakeProcess([
            {"result":{"userAgent":"private","codexHome":"/private","platformFamily":"unix","platformOs":"linux"}},
            {"result":{"data":[],"nextCursor":None}},
        ])
        original = self.home.with_name("authorized-home")
        def popen(argv, **kwargs):
            self.home.rename(original)
            self.home.mkdir()
            home_fd = kwargs["pass_fds"][1]
            observed["home_fd"] = home_fd
            observed["home_env"] = kwargs["env"]["HOME"]
            observed["identity"] = (os.stat(kwargs["env"]["HOME"]).st_dev,
                                    os.stat(kwargs["env"]["HOME"]).st_ino)
            observed["authorized"] = (os.stat(original).st_dev, os.stat(original).st_ino)
            observed["replacement"] = (os.stat(self.home).st_dev, os.stat(self.home).st_ino)
            return fake
        self._client(_popen=popen).list_one_page()
        self.assertEqual(observed["home_env"], f"/proc/self/fd/{observed['home_fd']}")
        self.assertEqual(observed["identity"], observed["authorized"])
        self.assertNotEqual(observed["identity"], observed["replacement"])
        with self.assertRaises(OSError): os.fstat(observed["home_fd"])

    def test_home_symlink_and_non_directory_fail_closed(self):
        target = self.home.with_name("target-home")
        self.home.rename(target)
        self.home.symlink_to(target, target_is_directory=True)
        with self.assertRaises(InvalidTargetError): self._client()._validate()
        self.home.unlink(); self.home.write_text("not a directory")
        with self.assertRaises(InvalidTargetError): self._client()._validate()

    def test_strict_integration_shapes_require_every_serialized_member(self):
        initialize = {"userAgent":"ua","codexHome":"/home","platformFamily":"unix","platformOs":"linux"}
        for key in tuple(initialize):
            invalid = dict(initialize); invalid.pop(key)
            with self.subTest(structure="initialize", key=key), self.assertRaises(ValueError):
                self._client()._validate_initialize_result(invalid)
        valid_project = project(roots=[{"path":"/root"}])
        response = {"data":[valid_project], "nextCursor":None}
        for key in ("data", "nextCursor"):
            invalid = dict(response); invalid.pop(key)
            with self.subTest(structure="response", key=key), self.assertRaises(ValueError):
                self._client()._validate_project_list_result(invalid)
        for key in tuple(valid_project):
            invalid_project = dict(valid_project); invalid_project.pop(key)
            with self.subTest(structure="project", key=key), self.assertRaises(ValueError):
                self._client()._validate_project_list_result({"data":[invalid_project],"nextCursor":None})
        with self.assertRaises(ValueError):
            self._client()._validate_project_list_result(
                {"data":[project(roots=[{}])],"nextCursor":None})
        self._client()._validate_project_list_result(response)
        self.assertIsNone(valid_project["recencyAt"])

    def test_unchanged_executable_identity_allows_fake_launch(self):
        actual = os.lstat(self.exe)
        result, fake = self._run([])
        self.assertEqual(result.summary.target_revision_mapping, "NOT_ESTABLISHED")
        self.assertEqual(len(fake.requests), 3)
        self.assertEqual((actual.st_dev, actual.st_ino),
                         (os.lstat(self.exe).st_dev, os.lstat(self.exe).st_ino))

    def test_non_regular_path_is_rejected_before_open(self):
        regular = os.lstat(self.exe)
        non_regular_modes = (
            stat.S_IFIFO | 0o700,
            stat.S_IFDIR | 0o700,
            stat.S_IFSOCK | 0o700,
            stat.S_IFCHR | 0o700,
            stat.S_IFLNK | 0o700,
        )
        for mode in non_regular_modes:
            with self.subTest(mode=mode), mock.patch(
                    "codex_wsl_rpc.integration.client.os.open") as opened:
                path_status = mock.Mock(
                    st_mode=mode, st_dev=regular.st_dev, st_ino=regular.st_ino
                )
                with self.assertRaises(UnsupportedTargetError):
                    self._client(_lstat=lambda path, value=path_status: value)._validate()
                opened.assert_not_called()

    def test_validation_open_is_nonblocking_and_rejects_replaced_fifo(self):
        path_status = os.lstat(self.exe)
        opened_status = mock.Mock(
            st_mode=stat.S_IFIFO | 0o700,
            st_dev=path_status.st_dev,
            st_ino=path_status.st_ino,
        )
        with mock.patch("codex_wsl_rpc.integration.client.os.open", return_value=91) as opened, \
                mock.patch("codex_wsl_rpc.integration.client.os.fstat", return_value=opened_status), \
                mock.patch("codex_wsl_rpc.integration.client.os.pread") as pread, \
                mock.patch("codex_wsl_rpc.integration.client.os.close") as closed:
            with self.assertRaises(UnsupportedTargetError):
                self._client()._validate()
        flags = opened.call_args.args[1]
        self.assertEqual(flags & getattr(os, "O_NONBLOCK", 0),
                         getattr(os, "O_NONBLOCK", 0))
        self.assertEqual(flags & getattr(os, "O_NOFOLLOW", 0),
                         getattr(os, "O_NOFOLLOW", 0))
        pread.assert_not_called()
        closed.assert_called_once_with(91)

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

    def test_missing_next_cursor_fails_closed_without_success_evidence(self):
        fake=FakeProcess([
            {"id":1,"result":{"userAgent":"private","codexHome":"/private","platformFamily":"unix","platformOs":"linux"}},
            {"id":2,"result":{"data":[]}},
        ])
        client=self._client(_popen=lambda *a,**k: fake)
        with self.assertRaisesRegex(IntegrationError, "^project/list protocol error$") as caught:
            client.list_one_page()
        rendered=json.dumps({"status":"failed", "category":caught.exception.category})
        self.assertNotIn("project_list_succeeded", rendered)
        self.assertNotIn("has_more", rendered)
        self.assertNotIn("data", rendered)

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
                self.assertEqual(self._client()._cleanup(state), expected)
                self.assertTrue(state.completed)
                self.assertEqual(process.terminate.call_count, terminates)
                self.assertEqual(process.kill.call_count, kills)

    def test_cleanup_requires_reap_and_stdout_eof_at_expired_deadline(self):
        process = CleanupProcess([])
        process.returncode = 0
        transport = TerminalCleanupTransport([(True, False)])
        state = _OwnedChildCleanup(process, transport)

        with self.assertRaisesRegex(CleanupError, "owned-child cleanup failed"):
            self._client(_clock=ScriptedClock([0.0, 0.0, 7.0]))._cleanup(state)

        self.assertFalse(state.completed)
        self.assertIs(state.process, process)
        self.assertTrue(transport.closed)
        process.terminate.assert_not_called()
        process.kill.assert_not_called()

    def test_cleanup_completes_only_after_reap_and_stdout_eof(self):
        process = CleanupProcess([])
        process.returncode = 0
        transport = TerminalCleanupTransport([(True, True)])
        state = _OwnedChildCleanup(process, transport)

        self.assertEqual(
            self._client(_clock=ScriptedClock([0.0, 0.0, 7.0]))._cleanup(state),
            "graceful",
        )

        self.assertTrue(state.completed)
        self.assertIsNone(state.process)
        self.assertTrue(transport.closed)

    def test_cleanup_retries_interrupted_mask_acquisition_before_starting(self):
        for interruptions in (1, 3):
            with self.subTest(interruptions=interruptions):
                process = CleanupProcess([0])
                state = _OwnedChildCleanup(process, None)
                attempts = 0
                def sigmask(operation, mask):
                    nonlocal attempts
                    if operation == signal.SIG_BLOCK:
                        attempts += 1
                        self.assertFalse(state.started)
                        if attempts <= interruptions:
                            raise KeyboardInterrupt()
                        return set()
                    return None
                with self.assertRaises(OperatorCancelledError):
                    self._client(_sigmask=sigmask)._cleanup(state)
                self.assertEqual(attempts, interruptions + 1)
                self.assertTrue(state.completed)
                self.assertIsNone(state.process)

    def test_finally_cleanup_retries_interrupted_mask_acquisition(self):
        process = CleanupProcess([0])
        transport = mock.Mock()
        transport.send.side_effect = TransportError("fake")
        cleanup_blocks = 0
        total_blocks = 0
        def sigmask(operation, mask):
            nonlocal cleanup_blocks, total_blocks
            if operation == signal.SIG_BLOCK:
                total_blocks += 1
                if total_blocks > 1:
                    cleanup_blocks += 1
                    if cleanup_blocks == 1:
                        raise KeyboardInterrupt()
                return set()
            return None
        client = self._client(_popen=lambda *a, **k: process, _sigmask=sigmask)
        with mock.patch("codex_wsl_rpc.integration.client._StreamTransport",
                        return_value=transport):
            with self.assertRaises(OperatorCancelledError):
                client.list_one_page()
        self.assertEqual(cleanup_blocks, 2)
        self.assertIsNotNone(process.returncode)

    def test_cleanup_failure_precedes_cancellation_deferred_during_mask(self):
        process = CleanupProcess([subprocess.TimeoutExpired("fake", 1)] * 3)
        state = _OwnedChildCleanup(process, None)
        attempts = 0
        def sigmask(operation, mask):
            nonlocal attempts
            if operation == signal.SIG_BLOCK:
                attempts += 1
                if attempts == 1:
                    raise KeyboardInterrupt()
                return set()
            return None
        with self.assertRaises(CleanupError):
            self._client(_sigmask=sigmask)._cleanup(state)
        self.assertEqual(attempts, 2)
        self.assertFalse(state.completed)
        process.terminate.assert_called_once_with()
        process.kill.assert_called_once_with()

    def test_cleanup_masks_sigint_through_final_bookkeeping_and_restores(self):
        blocked = False
        events = []
        def sigmask(operation, mask):
            nonlocal blocked
            events.append((operation, blocked))
            if operation == signal.SIG_BLOCK:
                blocked = True
                return {signal.SIGTERM}
            self.assertTrue(blocked)
            self.assertEqual(mask, {signal.SIGTERM})
            blocked = False
        process = CleanupProcess([
            subprocess.TimeoutExpired("fake", 1),
            subprocess.TimeoutExpired("fake", 1),
            0,
        ])
        process.stdin.close.side_effect = lambda: self.assertTrue(blocked)
        process.terminate.side_effect = lambda: self.assertTrue(blocked)
        process.kill.side_effect = lambda: self.assertTrue(blocked)
        transport = mock.Mock()
        transport.close.side_effect = lambda: self.assertTrue(blocked)
        state = _OwnedChildCleanup(process, transport)
        self.assertEqual(self._client(_sigmask=sigmask)._cleanup(state),
                         "killed_owned_child")
        self.assertTrue(state.completed)
        self.assertFalse(blocked)
        self.assertEqual([event[0] for event in events],
                         [signal.SIG_BLOCK, signal.SIG_SETMASK])

    def test_cleanup_mask_acquisition_has_fixed_bound_and_one_deadline(self):
        clock = mock.Mock(return_value=0.0)
        sigmask = mock.Mock(side_effect=KeyboardInterrupt())
        state = _OwnedChildCleanup(CleanupProcess([0]), None)
        with self.assertRaisesRegex(CleanupError, "protection failed"):
            self._client(_clock=clock, _sigmask=sigmask)._cleanup(state)
        self.assertEqual(sigmask.call_count, 4)
        self.assertFalse(state.started)
        self.assertFalse(state.completed)
        self.assertTrue(state.protection_failed)
        # One deadline origin plus one non-resetting bound check per attempt.
        self.assertEqual(clock.call_count, 5)

    def test_cleanup_mask_acquisition_respects_cleanup_wide_deadline(self):
        clock = ScriptedClock([0.0, 7.0])
        sigmask = mock.Mock()
        state = _OwnedChildCleanup(CleanupProcess([0]), None)
        with self.assertRaisesRegex(CleanupError, "protection failed"):
            self._client(_clock=clock, _sigmask=sigmask)._cleanup(state)
        sigmask.assert_not_called()
        self.assertTrue(state.protection_failed)

    def test_cleanup_restores_mask_before_deferred_cancel_and_after_failure(self):
        for waits, expected in (([0], OperatorCancelledError),
                                ([subprocess.TimeoutExpired("fake", 1)] * 3, CleanupError)):
            with self.subTest(expected=expected.__name__):
                restored = False
                def sigmask(operation, mask):
                    nonlocal restored
                    if operation == signal.SIG_BLOCK:
                        return set()
                    restored = True
                    if expected is OperatorCancelledError:
                        raise KeyboardInterrupt()
                state = _OwnedChildCleanup(CleanupProcess(waits), None)
                with self.assertRaises(expected):
                    self._client(_sigmask=sigmask)._cleanup(state)
                self.assertTrue(restored)
                if expected is OperatorCancelledError:
                    self.assertTrue(state.completed)

    def test_cleanup_raises_when_owned_child_cannot_be_reaped(self):
        process=CleanupProcess([subprocess.TimeoutExpired("fake", 1)] * 3)
        with self.assertRaisesRegex(IntegrationError, "owned-child cleanup failed"):
            self._client()._cleanup(_OwnedChildCleanup(process, None))
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
        terminated = False
        fake.poll = lambda: 0 if terminated else None
        def terminate():
            nonlocal terminated
            terminated = True
        fake.terminate = mock.Mock(side_effect=terminate)
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
                    self._client()._cleanup(state)
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
            self._client()._cleanup(state)
        self.assertTrue(state.started)
        self.assertFalse(state.completed)
        process.terminate.assert_called_once_with()
        process.kill.assert_called_once_with()

    def test_close_failures_do_not_suppress_bounded_escalation(self):
        cases = (
            (True, False, [subprocess.TimeoutExpired("fake", 1), 0], 1, 0),
            (False, True, [subprocess.TimeoutExpired("fake", 1), 0], 1, 0),
            (True, False, [subprocess.TimeoutExpired("fake", 1), subprocess.TimeoutExpired("fake", 1), 0], 1, 1),
            (True, True, [subprocess.TimeoutExpired("fake", 1), subprocess.TimeoutExpired("fake", 1), 0], 1, 1),
        )
        for transport_fails, stdin_fails, waits, terminates, kills in cases:
            with self.subTest(transport=transport_fails, stdin=stdin_fails, kills=kills):
                process = CleanupProcess(waits)
                transport = mock.Mock()
                if transport_fails: transport.close.side_effect = OSError("close")
                if stdin_fails: process.stdin.close.side_effect = OSError("close")
                state = _OwnedChildCleanup(process, transport)
                with self.assertRaises(CleanupError): self._client()._cleanup(state)
                self.assertTrue(state.completed)
                self.assertIsNone(state.process)
                self.assertEqual(process.terminate.call_count, terminates)
                self.assertEqual(process.kill.call_count, kills)

    def test_reaped_child_with_close_diagnostics_is_not_signalled(self):
        process = CleanupProcess([0]); transport = mock.Mock()
        transport.close.side_effect = OSError("close")
        with self.assertRaises(CleanupError):
            self._client()._cleanup(_OwnedChildCleanup(process, transport))
        process.terminate.assert_not_called(); process.kill.assert_not_called()

    def test_cleanup_interrupt_retries_share_each_absolute_stage_deadline(self):
        clock = FakeClock()
        waits = [
            (KeyboardInterrupt(), 1.9), (KeyboardInterrupt(), .1),
            (subprocess.TimeoutExpired("fake", 1), 2.0),
            (KeyboardInterrupt(), 1.5), (KeyboardInterrupt(), .5),
        ]
        process = TimedCleanupProcess(clock, waits)
        state = _OwnedChildCleanup(process, None)
        with self.assertRaises(CleanupError):
            self._client(_clock=clock)._cleanup(state)
        self.assertEqual(len(process.timeouts), 5)
        self.assertAlmostEqual(process.timeouts[0], 2.0)
        self.assertAlmostEqual(process.timeouts[1], .1)
        self.assertAlmostEqual(process.timeouts[2], 2.0)
        self.assertAlmostEqual(process.timeouts[3], 2.0)
        self.assertAlmostEqual(process.timeouts[4], .5)
        process.terminate.assert_called_once_with(); process.kill.assert_called_once_with()

    def test_cleanup_defers_clock_interrupts_across_entire_state_machine(self):
        # Interrupt before the first deadline, while calculating graceful
        # remaining time, and around both later deadline transitions.
        clock = ScriptedClock([
            KeyboardInterrupt(), 0.0, KeyboardInterrupt(), 0.0,
            KeyboardInterrupt(), 2.0, KeyboardInterrupt(), 2.0,
            KeyboardInterrupt(), 4.0, KeyboardInterrupt(), 4.0,
        ])
        process = CleanupProcess([
            subprocess.TimeoutExpired("fake", 1),
            subprocess.TimeoutExpired("fake", 1),
            0,
        ])
        state = _OwnedChildCleanup(process, None)
        with self.assertRaises(OperatorCancelledError):
            self._client(_clock=clock)._cleanup(state)
        self.assertTrue(state.completed)
        self.assertIsNone(state.process)
        process.terminate.assert_called_once_with()
        process.kill.assert_called_once_with()

    def test_cleanup_defers_interrupts_between_escalation_transitions(self):
        process = CleanupProcess([
            subprocess.TimeoutExpired("fake", 1),
            subprocess.TimeoutExpired("fake", 1),
            0,
        ])
        process.terminate.side_effect = KeyboardInterrupt()
        process.kill.side_effect = KeyboardInterrupt()
        state = _OwnedChildCleanup(process, None)
        with self.assertRaises(OperatorCancelledError):
            self._client()._cleanup(state)
        self.assertTrue(state.completed)
        self.assertEqual(process.terminate.call_count, 2)
        self.assertEqual(process.kill.call_count, 0)
        self.assertIs(state.terminate_state, _SignalDelivery.DELIVERY_UNCERTAIN)
        self.assertIs(state.kill_state, _SignalDelivery.NOT_ATTEMPTED)

    def test_uncertain_signal_delivery_is_bounded_and_reconciled(self):
        process = CleanupProcess([
            subprocess.TimeoutExpired("fake", 1),
            subprocess.TimeoutExpired("fake", 1),
            subprocess.TimeoutExpired("fake", 1),
            0,
        ])
        process.kill.side_effect = (KeyboardInterrupt(), None)
        state = _OwnedChildCleanup(process, None)
        with self.assertRaises(OperatorCancelledError):
            self._client()._cleanup(state)
        process.terminate.assert_called_once_with()
        self.assertEqual(process.kill.call_count, 2)
        self.assertIs(state.terminate_state, _SignalDelivery.DELIVERED)
        self.assertIs(state.kill_state, _SignalDelivery.DELIVERED)
        self.assertTrue(state.completed)

    def test_cleanup_failure_precedes_deferred_clock_cancellation(self):
        clock = ScriptedClock([
            KeyboardInterrupt(), 0.0, 2.0,
            KeyboardInterrupt(), 2.0, 4.0,
            KeyboardInterrupt(), 4.0, 6.0,
        ])
        process = CleanupProcess([])
        state = _OwnedChildCleanup(process, None)
        with self.assertRaises(CleanupError):
            self._client(_clock=clock)._cleanup(state)
        self.assertTrue(state.started)
        self.assertFalse(state.completed)
        process.terminate.assert_called_once_with()
        process.kill.assert_called_once_with()

    def test_transport_construction_failure_keeps_exact_child_owned(self):
        failure_points = ("selector factory", "stdout blocking", "stderr blocking",
                          "stdout register", "stderr register", "stdin blocking")
        for point in failure_points:
            with self.subTest(point=point):
                process = CleanupProcess([0])
                client = self._client(_popen=lambda *a, **k: process)
                with mock.patch("codex_wsl_rpc.integration.client._StreamTransport",
                                side_effect=OSError(point)):
                    with self.assertRaises(StartupError): client.list_one_page()
                process.stdin.close.assert_called_once_with()
                process.terminate.assert_not_called(); process.kill.assert_not_called()

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
        accepted = ("4.4.0-19041-Microsoft", "5.15.90.1-mIcRoSoFt-standard-WSL2")
        for release in accepted:
            with self.subTest(release=release):
                client=self._client(_proc_reader=lambda path, text=release: text)
                self.assertTrue(client._is_wsl())
        rejected = (("linux", "6.8.0-ubuntu-generic"), ("linux", "6.8.0-container"),
                    ("win32", "5.15.90.1-microsoft-standard-WSL2"),
                    ("darwin", "5.15.90.1-microsoft-standard-WSL2"))
        for platform, release in rejected:
            with self.subTest(platform=platform, release=release):
                popen=mock.Mock()
                client=self._client(_platform=platform, _proc_reader=lambda path, text=release: text,
                                    _popen=popen)
                with self.assertRaises(UnsupportedPlatformError): client.list_one_page()
                popen.assert_not_called()

    def test_wsl_kernel_release_grammar_fails_closed(self):
        accepted = ("5.15.90.1-microsoft-standard-WSL2",
                    "5.15.90.1-microsoft-standard-WSL2\n",
                    "4.19.104-microsoft-standard", "4.4.0-19041-Microsoft",
                    "5.10.0-WSL2")
        rejected = ("", "not-a-kernel-release", "6.8.0-ubuntu-generic",
                    "linux-built-by-microsoft-example",
                    "6.8.0-linux-built-by-microsoft-example",
                    "6.8.0-wsl-build-metadata",
                    "5.15.90.1-mİcrosoft-standard-WSL2",
                    " 5.15.90.1-microsoft-standard-WSL2",
                    "5.15.90.1-microsoft-standard-WSL2\n\n")
        for release in accepted:
            with self.subTest(release=release):
                self.assertTrue(_is_wsl_kernel_release(release))
        for release in rejected:
            with self.subTest(release=release):
                self.assertFalse(_is_wsl_kernel_release(release))

    def test_proc_version_metadata_never_authorizes_wsl(self):
        for metadata in ("Linux version 6.8.0 (builder@microsoft.example) #1 SMP",
                         "Linux version 6.8.0 (compiler WSL toolchain) #1 SMP"):
            with self.subTest(metadata=metadata):
                reads = []
                def proc_reader(path):
                    reads.append(path)
                    if path == Path("/proc/sys/kernel/osrelease"):
                        return "6.8.0-ubuntu-generic"
                    return metadata
                self.assertFalse(self._client(_proc_reader=proc_reader)._is_wsl())
                self.assertEqual(reads, [Path("/proc/sys/kernel/osrelease")])

    def test_positive_wsl_detection_ignores_proc_version(self):
        reads = []
        def proc_reader(path):
            reads.append(path)
            if path == Path("/proc/sys/kernel/osrelease"):
                return "5.15.90.1-microsoft-standard-WSL2"
            raise AssertionError("/proc/version must not participate")
        self.assertTrue(self._client(_proc_reader=proc_reader)._is_wsl())
        self.assertEqual(reads, [Path("/proc/sys/kernel/osrelease")])

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
