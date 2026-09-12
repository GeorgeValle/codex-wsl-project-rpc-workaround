"""Focused orchestration tests for the opt-in packaging validator."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from _safety_support import repository_cache_dir


ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".cache"
SPEC = importlib.util.spec_from_file_location(
    "validate_packaging", ROOT / "tests/validate_packaging.py"
)
assert SPEC and SPEC.loader
validate_packaging = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validate_packaging)


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


class ImportInertnessTests(unittest.TestCase):
    def test_import_does_not_create_packaging_workspace(self):
        cache = repository_cache_dir(CACHE, ROOT)
        before = set(cache.iterdir())
        spec = importlib.util.spec_from_file_location(
            "validate_packaging_second_import", ROOT / "tests/validate_packaging.py"
        )
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(set(cache.iterdir()), before)


if __name__ == "__main__":
    unittest.main()
