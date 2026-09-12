"""Repository-local tests for the non-functional packaging foundation."""

from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path
import stat
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
WHEELHOUSE = CACHE / "codex-wsl-rpc-wheelhouse"
PACKAGING_TMP = CACHE / "codex-wsl-rpc-packaging-tmp"
SETUPTOOLS_VERSION = "84.0.0"
SETUPTOOLS_WHEEL = "setuptools-84.0.0-py3-none-any.whl"
SETUPTOOLS_SHA256 = (
    "51a52592b3b99e102b609654876bd65f19f999935166d1352678931132b0c670"
)
IMPORT_PROBE_TIMEOUT_SECONDS = 10


def repository_cache_dir(cache: Path = CACHE, root: Path = ROOT) -> Path:
    """Return a validated repository-local cache directory."""

    resolved_root = root.resolve(strict=True)
    if cache.is_symlink():
        raise AssertionError("Repository cache path must not be a symbolic link")

    if cache.exists():
        if not cache.is_dir():
            raise AssertionError("Repository cache path exists but is not a directory")

        resolved_cache = cache.resolve(strict=True)
        if resolved_cache.parent != resolved_root:
            raise AssertionError(
                "Repository cache path resolves outside the repository root"
            )

        return resolved_cache

    resolved_parent = cache.parent.resolve(strict=True)
    if resolved_parent != resolved_root:
        raise AssertionError(
            "Repository cache parent resolves outside the repository root"
        )

    cache.mkdir()
    if cache.is_symlink():
        raise AssertionError("Repository cache path became a symbolic link")

    resolved_cache = cache.resolve(strict=True)
    if resolved_cache.parent != resolved_root:
        raise AssertionError(
            "Repository cache path resolves outside the repository root"
        )

    return resolved_cache


def repository_disposable_dir(
    path: Path,
    cache: Path = CACHE,
    root: Path = ROOT,
) -> Path:
    """Validate and create an exact disposable directory under the cache."""

    resolved_cache = repository_cache_dir(cache=cache, root=root)
    if path.is_symlink():
        raise AssertionError("Disposable path must not be a symbolic link")

    if path.exists():
        if not path.is_dir():
            raise AssertionError("Disposable path exists but is not a directory")

        resolved_path = path.resolve(strict=True)
        if resolved_path.parent != resolved_cache:
            raise AssertionError("Disposable path resolves outside the repository cache")
        return resolved_path

    resolved_parent = path.parent.resolve(strict=True)
    if resolved_parent != resolved_cache:
        raise AssertionError("Disposable path parent is not the repository cache")

    path.mkdir()
    if path.is_symlink():
        raise AssertionError("Disposable path became a symbolic link")

    resolved_path = path.resolve(strict=True)
    if resolved_path.parent != resolved_cache:
        raise AssertionError("Disposable path resolves outside the repository cache")
    return resolved_path


def validate_setuptools_wheelhouse(
    wheelhouse: Path = WHEELHOUSE,
    cache: Path = CACHE,
    root: Path = ROOT,
    expected_sha256: str = SETUPTOOLS_SHA256,
) -> Path:
    """Validate and return the sole approved local setuptools wheel."""

    resolved_cache = repository_cache_dir(cache=cache, root=root)
    if wheelhouse.is_symlink():
        raise AssertionError("Setuptools wheelhouse must not be a symbolic link")
    if not wheelhouse.exists():
        raise AssertionError("Setuptools wheelhouse does not exist")
    if not wheelhouse.is_dir():
        raise AssertionError("Setuptools wheelhouse is not a directory")

    resolved_wheelhouse = wheelhouse.resolve(strict=True)
    if resolved_wheelhouse.parent != resolved_cache:
        raise AssertionError(
            "Setuptools wheelhouse resolves outside the repository cache"
        )

    entries = list(os.scandir(resolved_wheelhouse))
    if len(entries) != 1:
        raise AssertionError("Wheelhouse must contain exactly one approved artifact")

    entry = entries[0]
    if entry.name != SETUPTOOLS_WHEEL:
        raise AssertionError(
            f"Wheelhouse artifact must be {SETUPTOOLS_WHEEL}; found {entry.name!r}"
        )
    if entry.is_symlink():
        raise AssertionError("Approved wheelhouse artifact must not be a symbolic link")
    if not stat.S_ISREG(entry.stat(follow_symlinks=False).st_mode):
        raise AssertionError("Approved wheelhouse artifact must be a regular file")

    wheel = Path(entry.path).resolve(strict=True)
    if wheel.parent != resolved_wheelhouse:
        raise AssertionError("Approved wheel resolves outside the validated wheelhouse")

    digest = hashlib.sha256()
    with wheel.open("rb") as artifact:
        for chunk in iter(lambda: artifact.read(1024 * 1024), b""):
            digest.update(chunk)
    actual_sha256 = digest.hexdigest()
    if actual_sha256 != expected_sha256:
        raise AssertionError(
            f"Setuptools wheel SHA-256 mismatch: expected {expected_sha256}, "
            f"found {actual_sha256}"
        )

    return wheel


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

    def test_out_of_root_cache_is_rejected_before_creation(self) -> None:
        cache = repository_cache_dir()
        with tempfile.TemporaryDirectory(prefix="cache-boundary-", dir=cache) as temporary:
            test_sandbox = Path(temporary)
            allowed_root = test_sandbox / "allowed-root"
            other_root = test_sandbox / "other-root"
            allowed_root.mkdir()
            other_root.mkdir()
            unauthorized_cache = other_root / ".cache"

            with self.assertRaisesRegex(AssertionError, "parent resolves outside"):
                repository_cache_dir(cache=unauthorized_cache, root=allowed_root)

            self.assertFalse(unauthorized_cache.exists())

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


class SetuptoolsWheelhouseTests(unittest.TestCase):
    def wheelhouse_sandbox(self) -> tempfile.TemporaryDirectory[str]:
        return tempfile.TemporaryDirectory(
            prefix="wheelhouse-boundary-", dir=repository_cache_dir()
        )

    def test_valid_local_wheelhouse_is_accepted(self) -> None:
        with self.wheelhouse_sandbox() as temporary:
            root = Path(temporary)
            cache = root / ".cache"
            cache.mkdir()
            wheelhouse = cache / "codex-wsl-rpc-wheelhouse"
            wheelhouse.mkdir()
            contents = b"controlled test wheel contents"
            wheel = wheelhouse / SETUPTOOLS_WHEEL
            wheel.write_bytes(contents)

            self.assertEqual(
                validate_setuptools_wheelhouse(
                    wheelhouse=wheelhouse,
                    cache=cache,
                    root=root,
                    expected_sha256=hashlib.sha256(contents).hexdigest(),
                ),
                wheel.resolve(strict=True),
            )

    def test_symbolic_link_wheelhouse_is_rejected(self) -> None:
        with self.wheelhouse_sandbox() as temporary:
            root = Path(temporary)
            cache = root / ".cache"
            cache.mkdir()
            target = cache / "controlled-target"
            target.mkdir()
            wheelhouse = cache / "codex-wsl-rpc-wheelhouse"
            try:
                wheelhouse.symlink_to(target, target_is_directory=True)
            except OSError as error:
                self.skipTest(f"symbolic-link creation is unavailable: {error}")

            with self.assertRaisesRegex(AssertionError, "must not be a symbolic link"):
                validate_setuptools_wheelhouse(
                    wheelhouse=wheelhouse, cache=cache, root=root
                )

    def test_missing_wheelhouse_is_rejected(self) -> None:
        with self.wheelhouse_sandbox() as temporary:
            root = Path(temporary)
            cache = root / ".cache"
            cache.mkdir()
            wheelhouse = cache / "codex-wsl-rpc-wheelhouse"

            with self.assertRaisesRegex(AssertionError, "does not exist"):
                validate_setuptools_wheelhouse(
                    wheelhouse=wheelhouse, cache=cache, root=root
                )
            self.assertFalse(wheelhouse.exists())

    def test_wrong_setuptools_wheel_filename_is_rejected(self) -> None:
        with self.wheelhouse_sandbox() as temporary:
            root = Path(temporary)
            cache = root / ".cache"
            wheelhouse = cache / "codex-wsl-rpc-wheelhouse"
            wheelhouse.mkdir(parents=True)
            (wheelhouse / "setuptools-83.0.0-py3-none-any.whl").write_bytes(b"wheel")

            with self.assertRaisesRegex(AssertionError, "artifact must be"):
                validate_setuptools_wheelhouse(
                    wheelhouse=wheelhouse, cache=cache, root=root
                )

    def test_multiple_setuptools_candidates_are_rejected(self) -> None:
        with self.wheelhouse_sandbox() as temporary:
            root = Path(temporary)
            cache = root / ".cache"
            wheelhouse = cache / "codex-wsl-rpc-wheelhouse"
            wheelhouse.mkdir(parents=True)
            (wheelhouse / SETUPTOOLS_WHEEL).write_bytes(b"expected")
            (wheelhouse / "setuptools-85.0.0-py3-none-any.whl").write_bytes(
                b"additional"
            )

            with self.assertRaisesRegex(AssertionError, "exactly one approved"):
                validate_setuptools_wheelhouse(
                    wheelhouse=wheelhouse, cache=cache, root=root
                )

    def test_additional_regular_file_is_rejected(self) -> None:
        with self.wheelhouse_sandbox() as temporary:
            root = Path(temporary)
            cache = root / ".cache"
            wheelhouse = cache / "codex-wsl-rpc-wheelhouse"
            wheelhouse.mkdir(parents=True)
            (wheelhouse / SETUPTOOLS_WHEEL).write_bytes(b"expected")
            (wheelhouse / "unrelated.txt").write_text("unexpected", encoding="utf-8")

            with self.assertRaisesRegex(AssertionError, "exactly one approved"):
                validate_setuptools_wheelhouse(
                    wheelhouse=wheelhouse, cache=cache, root=root
                )

    def test_additional_symbolic_link_candidate_is_rejected(self) -> None:
        with self.wheelhouse_sandbox() as temporary:
            root = Path(temporary)
            cache = root / ".cache"
            wheelhouse = cache / "codex-wsl-rpc-wheelhouse"
            wheelhouse.mkdir(parents=True)
            approved = wheelhouse / SETUPTOOLS_WHEEL
            approved.write_bytes(b"expected")
            candidate = wheelhouse / "setuptools-85.0.0-py3-none-any.whl"
            try:
                candidate.symlink_to(approved.name)
            except OSError as error:
                self.skipTest(f"symbolic-link creation is unavailable: {error}")

            with self.assertRaisesRegex(AssertionError, "exactly one approved"):
                validate_setuptools_wheelhouse(
                    wheelhouse=wheelhouse, cache=cache, root=root
                )

    def test_expected_wheel_symbolic_link_is_rejected(self) -> None:
        with self.wheelhouse_sandbox() as temporary:
            root = Path(temporary)
            cache = root / ".cache"
            wheelhouse = cache / "codex-wsl-rpc-wheelhouse"
            wheelhouse.mkdir(parents=True)
            target = cache / "controlled-wheel-target"
            target.write_bytes(b"controlled target")
            wheel = wheelhouse / SETUPTOOLS_WHEEL
            try:
                wheel.symlink_to(target)
            except OSError as error:
                self.skipTest(f"symbolic-link creation is unavailable: {error}")

            with self.assertRaisesRegex(AssertionError, "must not be a symbolic link"):
                validate_setuptools_wheelhouse(
                    wheelhouse=wheelhouse, cache=cache, root=root
                )

    def test_directory_entry_is_rejected(self) -> None:
        with self.wheelhouse_sandbox() as temporary:
            root = Path(temporary)
            cache = root / ".cache"
            wheelhouse = cache / "codex-wsl-rpc-wheelhouse"
            wheelhouse.mkdir(parents=True)
            (wheelhouse / SETUPTOOLS_WHEEL).mkdir()

            with self.assertRaisesRegex(AssertionError, "must be a regular file"):
                validate_setuptools_wheelhouse(
                    wheelhouse=wheelhouse, cache=cache, root=root
                )

    def test_incorrect_sha256_is_rejected(self) -> None:
        with self.wheelhouse_sandbox() as temporary:
            root = Path(temporary)
            cache = root / ".cache"
            wheelhouse = cache / "codex-wsl-rpc-wheelhouse"
            wheelhouse.mkdir(parents=True)
            (wheelhouse / SETUPTOOLS_WHEEL).write_bytes(b"not the approved wheel")

            with self.assertRaisesRegex(AssertionError, "SHA-256 mismatch"):
                validate_setuptools_wheelhouse(
                    wheelhouse=wheelhouse, cache=cache, root=root
                )


class RepositoryDisposableDirectoryTests(unittest.TestCase):
    def disposable_sandbox(self) -> tempfile.TemporaryDirectory[str]:
        return tempfile.TemporaryDirectory(
            prefix="disposable-boundary-", dir=repository_cache_dir()
        )

    def test_valid_directory_under_controlled_cache_is_accepted(self) -> None:
        with self.disposable_sandbox() as temporary:
            root = Path(temporary)
            cache = root / ".cache"
            cache.mkdir()
            disposable = cache / "packaging-tmp"

            self.assertEqual(
                repository_disposable_dir(disposable, cache=cache, root=root),
                disposable.resolve(strict=True),
            )

    def test_symbolic_link_disposable_path_is_rejected(self) -> None:
        with self.disposable_sandbox() as temporary:
            root = Path(temporary)
            cache = root / ".cache"
            cache.mkdir()
            target = cache / "controlled-target"
            target.mkdir()
            disposable = cache / "packaging-tmp"
            try:
                disposable.symlink_to(target, target_is_directory=True)
            except OSError as error:
                self.skipTest(f"symbolic-link creation is unavailable: {error}")

            with self.assertRaisesRegex(AssertionError, "must not be a symbolic link"):
                repository_disposable_dir(disposable, cache=cache, root=root)

    def test_out_of_cache_path_is_rejected_before_creation(self) -> None:
        with self.disposable_sandbox() as temporary:
            root = Path(temporary)
            cache = root / ".cache"
            cache.mkdir()
            other = root / "other"
            other.mkdir()
            disposable = other / "packaging-tmp"

            with self.assertRaisesRegex(AssertionError, "parent is not"):
                repository_disposable_dir(disposable, cache=cache, root=root)

            self.assertFalse(disposable.exists())

    def test_existing_non_directory_disposable_path_is_rejected(self) -> None:
        with self.disposable_sandbox() as temporary:
            root = Path(temporary)
            cache = root / ".cache"
            cache.mkdir()
            disposable = cache / "packaging-tmp"
            disposable.write_text("not a directory", encoding="utf-8")

            with self.assertRaisesRegex(AssertionError, "is not a directory"):
                repository_disposable_dir(disposable, cache=cache, root=root)


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
import sys

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

sys.path.insert(0, os.environ["FOUNDATION_SRC"])

import codex_wsl_rpc

Path(os.environ["FOUNDATION_REPORT"]).write_text(
    json.dumps({"origin": str(Path(codex_wsl_rpc.__file__).resolve()), "invoked": invoked}),
    encoding="utf-8",
)
"""
            environment = {
                "APPDATA": str(state / "appdata"),
                "FOUNDATION_REPORT": str(report),
                "FOUNDATION_SRC": str(SRC),
                "HOME": str(home),
                "LOCALAPPDATA": str(state / "localappdata"),
                "PYTHONDONTWRITEBYTECODE": "1",
                "TEMP": str(temp_root),
                "TMP": str(temp_root),
                "TMPDIR": str(temp_root),
                "USERPROFILE": str(home),
            }
            for name in ("SYSTEMROOT", "SystemRoot", "WINDIR"):
                if name in os.environ:
                    environment[name] = os.environ[name]

            try:
                result = subprocess.run(
                    [sys.executable, "-S", "-c", probe],
                    cwd=work,
                    env=environment,
                    capture_output=True,
                    text=True,
                    check=False,
                    shell=False,
                    timeout=IMPORT_PROBE_TIMEOUT_SECONDS,
                )
            except subprocess.TimeoutExpired:
                self.fail(
                    "Guarded codex_wsl_rpc import probe exceeded "
                    f"{IMPORT_PROBE_TIMEOUT_SECONDS} seconds"
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
