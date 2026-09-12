"""Focused orchestration tests for the opt-in packaging validator."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from unittest import mock

from _safety_support import guarded_import_probe, repository_cache_dir


ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".cache"
VALIDATOR = ROOT / "tests/validate_packaging.py"
IMPORT_PROBE_TIMEOUT_SECONDS = 10
validate_packaging = None


def _tree_fingerprint(
    path: Path, *, ignored: frozenset[Path] = frozenset()
) -> tuple[tuple[str, str, str], ...]:
    """Fingerprint a controlled tree without following symlinks."""

    entries = []
    excluded = {".git", ".cache", "__pycache__"}
    for current, directories, files in os.walk(path, followlinks=False):
        current_path = Path(current)
        directories[:] = sorted(name for name in directories if name not in excluded)
        for name in directories + sorted(files):
            entry = current_path / name
            relative = entry.relative_to(path)
            if relative in ignored:
                continue
            if entry.is_symlink():
                entries.append((str(relative), "symlink", os.readlink(entry)))
            elif entry.is_file():
                entries.append((str(relative), "file", hashlib.sha256(entry.read_bytes()).hexdigest()))
            elif entry.is_dir():
                entries.append((str(relative), "directory", ""))
            else:
                entries.append((str(relative), "other", ""))
    return tuple(sorted(entries))


def _import_fingerprint(target: Path) -> tuple[object, object]:
    return _tree_fingerprint(ROOT), _tree_fingerprint(target.parent)


def _probe_first_import(target: Path) -> None:
    """Check a trusted test module's first import under targeted guards."""

    cache = repository_cache_dir(CACHE, ROOT)
    with tempfile.TemporaryDirectory(prefix="validator-import-", dir=cache) as temporary:
        sandbox = Path(temporary)
        work = sandbox / "work"
        home = sandbox / "home"
        temp_root = sandbox / "tmp"
        for directory in (work, home, temp_root):
            directory.mkdir()
        report = sandbox / "report.json"
        report.touch()
        before = (
            _tree_fingerprint(sandbox, ignored=frozenset({Path("report.json")})),
            _import_fingerprint(target),
        )
        probe = r'''
import importlib.util
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import tempfile

attempts = []
def prohibit(name):
    def guard(*args, **kwargs):
        attempts.append(name)
        raise RuntimeError("prohibited operation: " + name)
    return guard

socket.create_connection = prohibit("socket.create_connection")
socket.socket.connect = prohibit("socket.socket.connect")
subprocess.Popen = prohibit("subprocess.Popen")
os.system = prohibit("os.system")
sqlite3.connect = prohibit("sqlite3.connect")
tempfile.mkdtemp = prohibit("tempfile.mkdtemp")
os.mkdir = prohibit("os.mkdir")

error = None
try:
    import sys
    sys.path.insert(0, str(Path(os.environ["VALIDATOR_TARGET"]).parent))
    spec = importlib.util.spec_from_file_location("validator_first_import", os.environ["VALIDATOR_TARGET"])
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot create import specification")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
except BaseException as caught:
    error = f"{type(caught).__name__}: {caught}"
Path(os.environ["VALIDATOR_REPORT"]).write_text(
    json.dumps({"attempts": attempts, "error": error}), encoding="utf-8"
)
'''
        environment = {
            "HOME": str(home),
            "USERPROFILE": str(home),
            "APPDATA": str(home),
            "LOCALAPPDATA": str(home),
            "TMPDIR": str(temp_root),
            "TEMP": str(temp_root),
            "TMP": str(temp_root),
            "VALIDATOR_REPORT": str(report),
            "VALIDATOR_TARGET": str(target),
        }
        try:
            result = subprocess.run(
                [sys.executable, "-S", "-B", "-c", probe],
                cwd=work,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
                shell=False,
                timeout=IMPORT_PROBE_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as error:
            raise RuntimeError("Validator first-import probe timed out") from error
        observation = json.loads(report.read_text(encoding="utf-8"))
        after = (
            _tree_fingerprint(sandbox, ignored=frozenset({Path("report.json")})),
            _import_fingerprint(target),
        )
        if (result.returncode or result.stdout or result.stderr or
                observation["error"] or observation["attempts"] or after != before):
            raise RuntimeError(
                "Validator first-import probe failed: "
                f"returncode={result.returncode}, stdout={result.stdout!r}, "
                f"stderr={result.stderr!r}, observation={observation!r}, "
                f"filesystem_changed={after != before}"
            )


def _load_validator_after_probe(target: Path = VALIDATOR, loader=None):
    _probe_first_import(target)
    spec = importlib.util.spec_from_file_location("validate_packaging", target)
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot create validator import specification")
    module = importlib.util.module_from_spec(spec)
    attempts = []

    def prohibit(name):
        def guard(*args, **kwargs):
            attempts.append(name)
            raise RuntimeError("prohibited operation: " + name)
        return guard

    before = _import_fingerprint(target)
    stdout = io.StringIO()
    stderr = io.StringIO()
    original_cwd = Path.cwd()
    original_environment = dict(os.environ)
    original_dont_write_bytecode = sys.dont_write_bytecode
    try:
        sys.dont_write_bytecode = True
        with ExitStack() as patches, redirect_stdout(stdout), redirect_stderr(stderr):
            for owner, name, label in (
                (socket, "create_connection", "socket.create_connection"),
                (socket.socket, "connect", "socket.socket.connect"),
                (subprocess, "Popen", "subprocess.Popen"),
                (subprocess, "run", "subprocess.run"),
                (os, "system", "os.system"),
                (sqlite3, "connect", "sqlite3.connect"),
                (tempfile, "mkdtemp", "tempfile.mkdtemp"),
                (os, "mkdir", "os.mkdir"),
            ):
                patches.enter_context(mock.patch.object(owner, name, prohibit(label)))
            (loader or spec.loader.exec_module)(module)
    finally:
        sys.dont_write_bytecode = original_dont_write_bytecode
        os.chdir(original_cwd)
        os.environ.clear()
        os.environ.update(original_environment)
    after = _import_fingerprint(target)
    if attempts or stdout.getvalue() or stderr.getvalue() or after != before:
        raise RuntimeError(
            "Guarded validator load failed: "
            f"attempts={attempts!r}, stdout={stdout.getvalue()!r}, "
            f"stderr={stderr.getvalue()!r}, filesystem_changed={after != before}"
        )
    return module


def setUpModule() -> None:
    global validate_packaging
    validate_packaging = _load_validator_after_probe()


class FixtureMixin:
    def sandbox(self):
        return tempfile.TemporaryDirectory(
            prefix="packaging-script-test-",
            dir=repository_cache_dir(CACHE, ROOT),
        )

    def project_fixture(self, parent: Path) -> tuple[Path, Path, Path]:
        root = parent / "repo"
        source = root / "src/codex_wsl_rpc"
        source.mkdir(parents=True)
        for name, contents in {
            "pyproject.toml": "[build-system]\nrequires=['setuptools']\n",
            "README.md": "readme\n",
            "LICENSE": "license\n",
        }.items():
            (root / name).write_text(contents, encoding="utf-8")
        (source / "__init__.py").write_text('__version__ = "0.0.0"\n', encoding="utf-8")
        cache = root / ".cache"
        cache.mkdir()
        wheelhouse = cache / "codex-wsl-rpc-wheelhouse"
        wheelhouse.mkdir()
        return root, source.parent, wheelhouse


class SourceSelectionTests(FixtureMixin, unittest.TestCase):
    def test_unreadable_directory_stops_selection_and_orchestration(self):
        with self.sandbox() as temporary:
            area = Path(temporary)
            root, source, wheelhouse = self.project_fixture(area)
            blocked = source / "codex_wsl_rpc/blocked"
            blocked.mkdir()
            original_error = PermissionError(13, "denied", str(blocked))
            real_scandir = os.scandir

            def fail_specific(path):
                if Path(path) == blocked:
                    raise original_error
                return real_scandir(path)

            with mock.patch.object(validate_packaging.os, "scandir", side_effect=fail_specific):
                with self.assertRaises(validate_packaging.ValidationError) as raised:
                    validate_packaging.selected_source_files(root, source)
                self.assertIs(raised.exception.__cause__, original_error)

                runner = mock.Mock()
                workspace = area / "workspace"
                workspace.mkdir()
                with self.assertRaises(validate_packaging.ValidationError):
                    validate_packaging.execute(
                        workspace, runner=runner, root=root, wheelhouse=wheelhouse
                    )
                runner.assert_not_called()

    def test_source_root_and_nested_symlinks_fail_before_runner(self):
        for nested in (False, True):
            with self.subTest(nested=nested), self.sandbox() as temporary:
                area = Path(temporary)
                root, source, wheelhouse = self.project_fixture(area)
                target = area / "target"
                target.mkdir()
                link = source / "linked" if nested else source
                if not nested:
                    source.rename(area / "original-src")
                try:
                    link.symlink_to(target, target_is_directory=True)
                except OSError as error:
                    self.skipTest(f"symbolic-link creation unavailable: {error}")
                runner = mock.Mock()
                with self.assertRaises(validate_packaging.ValidationError):
                    validate_packaging.selected_source_files(root, source)
                runner.assert_not_called()

    def test_generated_inputs_are_skipped_but_authored_files_are_copied_byte_for_byte(self):
        with self.sandbox() as temporary:
            area = Path(temporary)
            root, source, _ = self.project_fixture(area)
            (source / "codex_wsl_rpc.egg-info").mkdir()
            (source / "__pycache__").mkdir()
            workspace = area / "workspace"
            workspace.mkdir()
            project = validate_packaging.copy_project(workspace, root, source)
            self.assertEqual(
                (project / "src/codex_wsl_rpc/__init__.py").read_bytes(),
                (source / "codex_wsl_rpc/__init__.py").read_bytes(),
            )
            self.assertFalse((project / "src/codex_wsl_rpc.egg-info").exists())

    def test_generated_metadata_symlink_is_skipped_and_untouched(self):
        with self.sandbox() as temporary:
            area = Path(temporary)
            root, source, _ = self.project_fixture(area)
            target = area / "generated-target"
            target.mkdir()
            marker = target / "keep"
            marker.write_text("unchanged", encoding="utf-8")
            generated = source / "codex_wsl_rpc.egg-info"
            try:
                generated.symlink_to(target, target_is_directory=True)
            except OSError as error:
                self.skipTest(f"symbolic-link creation unavailable: {error}")
            workspace = area / "workspace"
            workspace.mkdir()
            validate_packaging.copy_project(workspace, root, source)
            self.assertTrue(generated.is_symlink())
            self.assertEqual(marker.read_text(encoding="utf-8"), "unchanged")


class WheelhouseTests(FixtureMixin, unittest.TestCase):
    def test_invalid_artifacts_fail_closed(self):
        cases = ("missing", "additional", "symlink", "wrong_hash")
        for case in cases:
            with self.subTest(case=case), self.sandbox() as temporary:
                area = Path(temporary)
                root, _, wheelhouse = self.project_fixture(area)
                wheel = wheelhouse / validate_packaging.SETUPTOOLS_WHEEL
                if case != "missing":
                    wheel.write_bytes(b"wrong")
                if case == "additional":
                    (wheelhouse / "other.whl").write_bytes(b"other")
                if case == "symlink":
                    wheel.unlink()
                    target = area / "target.whl"
                    target.write_bytes(b"wrong")
                    try:
                        wheel.symlink_to(target)
                    except OSError as error:
                        self.skipTest(f"symbolic-link creation unavailable: {error}")
                with self.assertRaises(validate_packaging.ValidationError):
                    validate_packaging.validate_provisioned_wheel(root / ".cache", wheelhouse)

    def test_approved_artifact_is_accepted_with_injected_digest(self):
        with self.sandbox() as temporary:
            area = Path(temporary)
            root, _, wheelhouse = self.project_fixture(area)
            wheel = wheelhouse / validate_packaging.SETUPTOOLS_WHEEL
            wheel.write_bytes(b"fixture")
            with mock.patch.object(
                validate_packaging, "SETUPTOOLS_SHA256", hashlib.sha256(b"fixture").hexdigest()
            ):
                self.assertEqual(
                    validate_packaging.validate_provisioned_wheel(root / ".cache", wheelhouse),
                    wheel.resolve(),
                )


class OrchestrationTests(FixtureMixin, unittest.TestCase):
    def test_two_main_runs_allocate_distinct_workspaces(self):
        cache = repository_cache_dir(CACHE, ROOT)
        workspaces = []

        def fake_execute(workspace):
            workspaces.append(workspace)

        with mock.patch.object(validate_packaging, "execute", side_effect=fake_execute):
            self.assertEqual(validate_packaging.main(), 0)
            self.assertEqual(validate_packaging.main(), 0)
        self.assertEqual(len(set(workspaces)), 2)
        self.assertTrue(all(not path.exists() for path in workspaces))
        self.assertEqual(cache, CACHE.resolve())

    def test_failure_retains_owned_workspace_and_unrelated_paths(self):
        cache = repository_cache_dir(CACHE, ROOT)
        unrelated = cache / "packaging-check-unrelated-fixture"
        unrelated.mkdir(exist_ok=True)
        (unrelated / "keep").write_text("keep", encoding="utf-8")
        retained = []

        def fail(workspace):
            retained.append(workspace)
            raise validate_packaging.ValidationError("expected")

        try:
            with mock.patch.object(validate_packaging, "execute", side_effect=fail):
                self.assertEqual(validate_packaging.main(), 1)
            self.assertTrue(retained[0].is_dir())
            self.assertEqual((unrelated / "keep").read_text(encoding="utf-8"), "keep")
        finally:
            # Test-owned fixtures only; production failure handling intentionally retains them.
            if retained and retained[0].is_dir():
                retained[0].rmdir()
            (unrelated / "keep").unlink()
            unrelated.rmdir()

    def test_commands_use_only_workspace_paths_and_controlled_environment(self):
        with self.sandbox() as temporary:
            area = Path(temporary)
            root, _, wheelhouse = self.project_fixture(area)
            wheel = wheelhouse / validate_packaging.SETUPTOOLS_WHEEL
            wheel.write_bytes(b"fixture")
            workspace = area / "workspace"
            workspace.mkdir()
            calls = []

            def runner(arguments, **kwargs):
                calls.append((arguments, kwargs))
                if arguments[1:3] == ["-m", "venv"]:
                    (workspace / "venv/bin").mkdir(parents=True)
                    (workspace / "venv/bin/python").touch()
                elif "-c" in arguments:
                    report = Path(kwargs["env"]["FOUNDATION_REPORT"])
                    report.write_text(json.dumps({
                        "origin": str((workspace / "project/src/codex_wsl_rpc/__init__.py").resolve()),
                        "invoked": [],
                        "filesystem_io": [],
                        "metadata": {"name": "codex-wsl-rpc", "version": "0.0.0",
                                     "requires_python": ">=3.11", "requires_dist": [],
                                     "entry_points": []},
                    }), encoding="utf-8")
                return subprocess.CompletedProcess(arguments, 0, "", "")

            with mock.patch.object(validate_packaging, "SETUPTOOLS_SHA256", hashlib.sha256(b"fixture").hexdigest()):
                validate_packaging.execute(workspace, runner=runner, root=root, wheelhouse=wheelhouse)
            self.assertEqual(len(calls), 3)
            for arguments, kwargs in calls:
                self.assertFalse(kwargs["shell"])
                self.assertGreater(kwargs["timeout"], 0)
                self.assertEqual(kwargs["env"]["PIP_CONFIG_FILE"], validate_packaging.os.devnull)
                self.assertNotIn("PYTHONPATH", kwargs["env"])
                for name in ("TMPDIR", "TEMP", "TMP", "HOME"):
                    self.assertTrue(Path(kwargs["env"][name]).is_relative_to(workspace))
            pip_arguments = calls[1][0]
            self.assertIn(str(workspace / "project"), pip_arguments)
            self.assertIn(str(workspace / "wheels"), pip_arguments)
            self.assertNotIn(str(root), pip_arguments)

    def test_timeout_becomes_validation_failure(self):
        def timeout(*args, **kwargs):
            raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

        with self.sandbox() as temporary:
            area = Path(temporary)
            environment = validate_packaging.controlled_environment(area)
            with self.assertRaisesRegex(validate_packaging.ValidationError, "timed out"):
                validate_packaging.run_checked(timeout, ["python"], cwd=area, environment=environment)


class RealProcessRunnerTests(FixtureMixin, unittest.TestCase):
    @unittest.skipUnless(sys.platform.startswith("linux"), "Linux process groups required")
    def test_successful_command(self):
        with self.sandbox() as temporary:
            area = Path(temporary)
            result = validate_packaging.run_process(
                [sys.executable, "-c", "print('ok')"], cwd=area,
                env={"PATH": os.defpath}, capture_output=True, text=True,
                check=False, shell=False, timeout=5,
            )
            self.assertEqual((result.returncode, result.stdout), (0, "ok\n"))

    @unittest.skipUnless(sys.platform.startswith("linux"), "Linux process groups required")
    def test_timeout_terminates_owned_group(self):
        process = mock.Mock(pid=43210)
        process.communicate.side_effect = [
            subprocess.TimeoutExpired(["python"], 1),
            ("", ""),
            ("", ""),
        ]
        with mock.patch.object(validate_packaging.subprocess, "Popen", return_value=process) as popen:
            with mock.patch.object(validate_packaging.os, "killpg") as killpg:
                with self.assertRaises(subprocess.TimeoutExpired):
                    validate_packaging.run_process(
                        ["python"], cwd=ROOT, env={}, capture_output=True,
                        text=True, check=False, shell=False, timeout=1,
                    )
        self.assertTrue(popen.call_args.kwargs["start_new_session"])
        self.assertEqual(killpg.call_args_list, [
            mock.call(43210, validate_packaging.signal.SIGTERM),
            mock.call(43210, validate_packaging.signal.SIGKILL),
        ])

    @unittest.skipUnless(sys.platform.startswith("linux"), "Linux process groups required")
    def test_descendant_cannot_finish_planned_work_after_timeout(self):
        with self.sandbox() as temporary:
            area = Path(temporary)
            marker = area / "descendant-finished"
            child = (
                "import os,pathlib,signal,time,sys; "
                "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
                "os.close(1); os.close(2); time.sleep(2); "
                "pathlib.Path(sys.argv[1]).write_text('bad')"
            )
            parent = (
                "import subprocess,sys,time; "
                "subprocess.Popen([sys.executable,'-c',sys.argv[1],sys.argv[2]]); "
                "time.sleep(30)"
            )
            with self.assertRaises(subprocess.TimeoutExpired):
                validate_packaging.run_process(
                    [sys.executable, "-c", parent, child, str(marker)], cwd=area,
                    env={"PATH": os.defpath}, capture_output=True, text=True,
                    check=False, shell=False, timeout=1,
                )
            time.sleep(2.5)
            self.assertFalse(marker.exists())


class ImportInertnessTests(FixtureMixin, unittest.TestCase):
    def run_package_probe(self, package_source: str, area: Path):
        package_root = area / "source"
        package = package_root / "codex_wsl_rpc"
        package.mkdir(parents=True)
        (package / "__init__.py").write_text(package_source, encoding="utf-8")
        report = area / "report.json"
        environment = {
            "FOUNDATION_ALLOWED_READ_ROOTS": json.dumps([str(package_root)]),
            "FOUNDATION_REPORT": str(report),
            "FOUNDATION_SRC": str(package_root),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        result = subprocess.run(
            [sys.executable, "-S", "-B", "-c", guarded_import_probe()],
            cwd=area, env=environment, capture_output=True, text=True,
            check=False, shell=False, timeout=IMPORT_PROBE_TIMEOUT_SECONDS,
        )
        return result, json.loads(report.read_text(encoding="utf-8"))

    def test_guarded_package_probe_rejects_filesystem_mutation(self):
        with self.sandbox() as temporary:
            area = Path(temporary)
            target = area / "owned.txt"
            target.write_text("keep", encoding="utf-8")
            result, observation = self.run_package_probe(
                "from pathlib import Path\n"
                "try:\n"
                f"    Path({str(target)!r}).unlink()\n"
                "except RuntimeError:\n"
                "    pass\n",
                area,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("os.remove", observation["denied_audit_events"])
            self.assertTrue(target.exists())

    def test_guarded_package_probe_rejects_dns_and_connectionless_network(self):
        cases = {
            "dns": (
                "import socket\ntry:\n"
                "    socket.getaddrinfo('localhost', 80)\n"
                "except RuntimeError:\n    pass\n"
            ),
            "connectionless": (
                "import socket\ntry:\n"
                "    socket.socket().sendto(b'x', ('127.0.0.1', 9))\n"
                "except RuntimeError:\n    pass\n"
            ),
        }
        for name, source in cases.items():
            with self.subTest(name=name), self.sandbox() as temporary:
                result, observation = self.run_package_probe(source, Path(temporary))
                self.assertNotEqual(result.returncode, 0)
                self.assertTrue(
                    observation["denied_audit_events"],
                    (result.returncode, result.stdout, result.stderr, observation),
                )
                self.assertTrue(all(event.startswith("socket.")
                                    for event in observation["denied_audit_events"]))

    def test_guarded_package_probe_allows_inert_module(self):
        with self.sandbox() as temporary:
            result, observation = self.run_package_probe(
                '__version__ = "0.0.0"\n', Path(temporary)
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(observation["denied_audit_events"], [])

    def test_guarded_package_probe_rejects_unrelated_file_read(self):
        with self.sandbox() as temporary:
            area = Path(temporary)
            package_root = area / "source"
            package = package_root / "codex_wsl_rpc"
            package.mkdir(parents=True)
            unrelated = area / "unrelated.txt"
            unrelated.write_text("controlled fixture", encoding="utf-8")
            (package / "__init__.py").write_text(
                "from pathlib import Path\n"
                "try:\n"
                f"    Path({str(unrelated)!r}).read_text(encoding='utf-8')\n"
                "except RuntimeError:\n"
                "    pass\n",
                encoding="utf-8",
            )
            report = area / "report.json"
            environment = {
                "FOUNDATION_ALLOWED_READ_ROOTS": json.dumps([str(package_root)]),
                "FOUNDATION_REPORT": str(report),
                "FOUNDATION_SRC": str(package_root),
                "PYTHONDONTWRITEBYTECODE": "1",
            }
            result = subprocess.run(
                [sys.executable, "-S", "-B", "-c", guarded_import_probe()],
                cwd=area,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
                shell=False,
                timeout=IMPORT_PROBE_TIMEOUT_SECONDS,
            )
            observation = json.loads(report.read_text(encoding="utf-8"))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("prohibited filesystem I/O observed", result.stderr)
            self.assertTrue(any(not item["allowed"] for item in observation["filesystem_io"]))

    def test_validator_import_rewrite_is_rejected_but_inert_import_succeeds(self):
        with self.sandbox() as temporary:
            area = Path(temporary)
            existing = area / "existing.txt"
            existing.write_text("before", encoding="utf-8")
            rewriting = area / "rewriting.py"
            rewriting.write_text(
                "from pathlib import Path\n"
                f"Path({str(existing)!r}).write_text('after', encoding='utf-8')\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(RuntimeError, "filesystem_changed"):
                _load_validator_after_probe(rewriting)

            inert = area / "inert.py"
            inert.write_text("VALUE = 1\n", encoding="utf-8")
            self.assertEqual(_load_validator_after_probe(inert).VALUE, 1)

    def test_parent_load_rejects_environment_conditional_operation_and_restores_guards(self):
        with self.sandbox() as temporary:
            fixture = Path(temporary) / "conditional_import.py"
            fixture.write_text(
                "import os\n"
                "if os.environ.get('VALIDATOR_PARENT_ATTEMPT'):\n"
                "    try:\n"
                "        os.system('never-executed')\n"
                "    except RuntimeError:\n"
                "        pass\n",
                encoding="utf-8",
            )
            original_system = os.system
            with mock.patch.dict(os.environ, {"VALIDATOR_PARENT_ATTEMPT": "1"}):
                with self.assertRaisesRegex(RuntimeError, "os.system"):
                    _load_validator_after_probe(fixture)
            self.assertIs(os.system, original_system)
            module = _load_validator_after_probe(fixture)
            self.assertIsNotNone(module)

    def test_first_import_probe_rejects_directory_creation(self):
        with self.sandbox() as temporary:
            fixture = Path(temporary) / "unsafe_import.py"
            fixture.write_text(
                "import tempfile\n"
                "try:\n"
                "    tempfile.mkdtemp(prefix='unsafe-import-')\n"
                "except RuntimeError:\n"
                "    pass\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(RuntimeError, "tempfile.mkdtemp"):
                _probe_first_import(fixture)

    def test_failed_probe_prevents_parent_loader(self):
        with self.sandbox() as temporary:
            fixture = Path(temporary) / "unsafe_import.py"
            fixture.write_text("import os\nos.mkdir('unsafe')\n", encoding="utf-8")
            loader = mock.Mock()
            with self.assertRaises(RuntimeError):
                _load_validator_after_probe(fixture, loader=loader)
            loader.assert_not_called()


if __name__ == "__main__":
    unittest.main()
