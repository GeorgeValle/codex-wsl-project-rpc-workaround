"""Repository-local tests for the non-functional packaging foundation."""

from __future__ import annotations

import ast
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"
SRC = (ROOT / "src").resolve()
PACKAGE = SRC / "codex_wsl_rpc"
CACHE = ROOT / ".cache"


def repository_cache_dir(cache: Path = CACHE, root: Path = ROOT) -> Path:
    """Return a validated repository-local cache directory."""

    resolved_root = root.resolve()
    if cache.is_symlink():
        raise AssertionError("Repository cache path must not be a symbolic link")
    if cache.exists() and not cache.is_dir():
        raise AssertionError("Repository cache path exists but is not a directory")

    cache.mkdir(exist_ok=True)
    resolved_cache = cache.resolve(strict=True)
    if resolved_cache.parent != resolved_root:
        raise AssertionError(
            "Repository cache path resolves outside the repository root"
        )

    return resolved_cache


def load_pyproject() -> dict[str, object]:
    """Load source metadata without requiring an installed distribution."""

    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))


def load_source_version() -> str:
    """Read the package version without executing package source."""

    tree = ast.parse((PACKAGE / "__init__.py").read_text(encoding="utf-8"))
    versions = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "__version__"
            for target in node.targets
        ):
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                versions.append(node.value.value)

    if len(versions) != 1:
        raise AssertionError("Expected exactly one literal __version__ assignment")

    return versions[0]


class SourceMetadataTests(unittest.TestCase):
    def test_project_metadata_and_dependency_policy(self) -> None:
        metadata = load_pyproject()
        project = metadata["project"]

        self.assertEqual(project["name"], "codex-wsl-rpc")
        self.assertEqual(project["version"], "0.0.0")
        self.assertEqual(project["requires-python"], ">=3.11")
        self.assertEqual(project["dependencies"], [])

    def test_build_backend_and_src_discovery(self) -> None:
        metadata = load_pyproject()

        self.assertEqual(metadata["build-system"]["build-backend"], "setuptools.build_meta")
        self.assertEqual(metadata["tool"]["setuptools"]["package-dir"], {"": "src"})
        self.assertEqual(metadata["tool"]["setuptools"]["packages"]["find"]["where"], ["src"])

    def test_no_cli_entry_point_is_configured(self) -> None:
        metadata = load_pyproject()
        project = metadata["project"]

        self.assertNotIn("scripts", project)
        self.assertNotIn("gui-scripts", project)
        self.assertNotIn("entry-points", project)
        self.assertNotIn("entry-points", metadata["tool"]["setuptools"])
        self.assertNotIn("script-files", metadata["tool"]["setuptools"])


class PackageStructureTests(unittest.TestCase):
    def test_only_src_package_exists(self) -> None:
        self.assertTrue((PACKAGE / "__init__.py").is_file())
        self.assertFalse((ROOT / "codex_wsl_rpc").exists())

    def test_source_version_matches_project_version(self) -> None:
        self.assertEqual(load_source_version(), load_pyproject()["project"]["version"])


class RepositoryCacheTests(unittest.TestCase):
    def test_repository_local_cache_directory_is_accepted(self) -> None:
        cache = repository_cache_dir()
        with tempfile.TemporaryDirectory(prefix="cache-boundary-", dir=cache) as temporary:
            test_root = Path(temporary)
            test_cache = test_root / ".cache"

            self.assertEqual(
                repository_cache_dir(cache=test_cache, root=test_root),
                test_cache.resolve(strict=True),
            )

    def test_existing_non_directory_cache_path_is_rejected(self) -> None:
        cache = repository_cache_dir()
        with tempfile.TemporaryDirectory(prefix="cache-boundary-", dir=cache) as temporary:
            test_root = Path(temporary)
            test_cache = test_root / ".cache"
            test_cache.write_text("not a directory", encoding="utf-8")

            with self.assertRaisesRegex(AssertionError, "is not a directory"):
                repository_cache_dir(cache=test_cache, root=test_root)

    def test_symbolic_link_cache_path_is_rejected(self) -> None:
        cache = repository_cache_dir()
        with tempfile.TemporaryDirectory(prefix="cache-boundary-", dir=cache) as temporary:
            test_root = Path(temporary)
            target = test_root / "target"
            target.mkdir()
            test_cache = test_root / ".cache"
            try:
                test_cache.symlink_to(target, target_is_directory=True)
            except OSError as error:
                self.skipTest(f"symbolic-link creation is unavailable: {error}")

            with self.assertRaisesRegex(AssertionError, "must not be a symbolic link"):
                repository_cache_dir(cache=test_cache, root=test_root)


class InertImportTests(unittest.TestCase):
    def test_import_is_inert_under_targeted_observation_guards(self) -> None:
        cache = repository_cache_dir()
        with tempfile.TemporaryDirectory(prefix="foundation-import-", dir=cache) as temporary:
            sandbox = Path(temporary)
            work = sandbox / "work"
            home = sandbox / "home"
            state = sandbox / "state"
            temp_root = sandbox / "tmp"
            report = sandbox / "report.json"
            for directory in (work, home, state, temp_root):
                directory.mkdir()

            probe = """
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess

invoked = []
def prohibited(name):
    def guard(*args, **kwargs):
        invoked.append(name)
        raise RuntimeError(f"prohibited primitive invoked: {name}")
    return guard

socket.create_connection = prohibited("socket.create_connection")
socket.socket.connect = prohibited("socket.socket.connect")
subprocess.Popen = prohibited("subprocess.Popen")
os.system = prohibited("os.system")
sqlite3.connect = prohibited("sqlite3.connect")

import codex_wsl_rpc

Path(os.environ["FOUNDATION_REPORT"]).write_text(
    json.dumps({"origin": str(Path(codex_wsl_rpc.__file__).resolve()), "invoked": invoked}),
    encoding="utf-8",
)
"""
            environment = {
                "APPDATA": str(state / "appdata"),
                "FOUNDATION_REPORT": str(report),
                "HOME": str(home),
                "LOCALAPPDATA": str(state / "localappdata"),
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONPATH": str(SRC),
                "TEMP": str(temp_root),
                "TMP": str(temp_root),
                "TMPDIR": str(temp_root),
                "USERPROFILE": str(home),
            }
            for name in ("SYSTEMROOT", "SystemRoot", "WINDIR"):
                if name in os.environ:
                    environment[name] = os.environ[name]

            result = subprocess.run(
                [sys.executable, "-c", probe],
                cwd=work,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
                shell=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "")
            self.assertEqual(result.stderr, "")
            observation = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(observation["origin"], str((PACKAGE / "__init__.py").resolve()))
            self.assertEqual(observation["invoked"], [])
            self.assertEqual(list(work.iterdir()), [])
            self.assertEqual(list(home.iterdir()), [])
            self.assertEqual(list(state.iterdir()), [])
            self.assertEqual(list(temp_root.iterdir()), [])
            self.assertEqual(
                set(sandbox.iterdir()), {work, home, state, temp_root, report}
            )


if __name__ == "__main__":
    unittest.main()
