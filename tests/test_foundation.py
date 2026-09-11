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


class InertImportTests(unittest.TestCase):
    def test_import_is_inert_under_targeted_observation_guards(self) -> None:
        CACHE.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="foundation-import-", dir=CACHE) as temporary:
            sandbox = Path(temporary)
            work = sandbox / "work"
            home = sandbox / "home"
            state = sandbox / "state"
            report = sandbox / "report.json"
            for directory in (work, home, state):
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
            self.assertEqual(set(sandbox.iterdir()), {work, home, state, report})


if __name__ == "__main__":
    unittest.main()
