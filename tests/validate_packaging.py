#!/usr/bin/env python3
"""Opt-in, offline packaging validation in one fresh owned workspace.

Importing this module is inert.  Run it explicitly from the repository root:
``python3 -B tests/validate_packaging.py``.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import signal
import shutil
import stat
import subprocess
import sys
import tempfile
from typing import Callable, Sequence

from _safety_support import guarded_import_probe, repository_cache_dir


ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".cache"
SOURCE_ROOT = ROOT / "src"
PROVISIONED_WHEELHOUSE = CACHE / "codex-wsl-rpc-wheelhouse"
SETUPTOOLS_VERSION = "84.0.0"
SETUPTOOLS_WHEEL = f"setuptools-{SETUPTOOLS_VERSION}-py3-none-any.whl"
SETUPTOOLS_SHA256 = "51a52592b3b99e102b609654876bd65f19f999935166d1352678931132b0c670"
TOP_LEVEL_INPUTS = ("pyproject.toml", "README.md", "LICENSE")
GENERATED_DIRECTORY_SUFFIXES = (".egg-info",)
SUBPROCESS_TIMEOUT_SECONDS = 120
PROBE_TIMEOUT_SECONDS = 10


class ValidationError(RuntimeError):
    """A packaging precondition or acceptance check failed."""


Runner = Callable[..., subprocess.CompletedProcess[str]]


def _stop_process_group(
    process: subprocess.Popen[str], process_group_id: int
) -> None:
    """Stop and reap the Linux process group owned by *process*, boundedly."""

    try:
        os.killpg(process_group_id, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.communicate(timeout=2)
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process_group_id, signal.SIGKILL)
    except ProcessLookupError:
        pass
    try:
        process.communicate(timeout=2)
    except subprocess.TimeoutExpired as error:
        raise ValidationError("Could not reap terminated packaging process group") from error


def run_process(arguments: Sequence[str], *, cwd: Path, env: dict[str, str],
                capture_output: bool, text: bool, check: bool, shell: bool,
                timeout: int) -> subprocess.CompletedProcess[str]:
    """Run one Linux/WSL command in an owned process group."""

    if not sys.platform.startswith("linux"):
        raise ValidationError(
            "Packaging validation requires Linux/WSL process-group semantics"
        )
    process = subprocess.Popen(
        list(arguments), cwd=cwd, env=env, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=text, shell=False, start_new_session=True,
    )
    process_group_id = process.pid
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _stop_process_group(process, process_group_id)
        raise
    except BaseException:
        _stop_process_group(process, process_group_id)
        raise
    return subprocess.CompletedProcess(arguments, process.returncode, stdout, stderr)


def _regular_file(path: Path, description: str) -> None:
    if path.is_symlink() or not path.is_file():
        raise ValidationError(f"{description} must be a regular non-symlink file: {path}")
    if not stat.S_ISREG(path.stat(follow_symlinks=False).st_mode):
        raise ValidationError(f"{description} is not a regular file: {path}")


def validate_source_root(root: Path = ROOT, source: Path = SOURCE_ROOT) -> Path:
    """Validate the lexical source path before resolving it."""

    resolved_root = root.resolve(strict=True)
    if source.is_symlink():
        raise ValidationError("Source root must not be a symbolic link")
    if not source.exists() or not source.is_dir():
        raise ValidationError("Source root must be an existing directory")
    resolved_source = source.resolve(strict=True)
    if resolved_source.parent != resolved_root:
        raise ValidationError("Source root is not a direct child of the repository root")
    return resolved_source


def selected_source_files(root: Path = ROOT, source: Path = SOURCE_ROOT) -> list[Path]:
    """Select all authored files for the current, deliberately small package."""

    resolved_source = validate_source_root(root, source)
    selected: list[Path] = []
    for name in TOP_LEVEL_INPUTS:
        path = root / name
        _regular_file(path, "Top-level packaging input")
        selected.append(path)

    def fail_walk(error: OSError) -> None:
        raise ValidationError(
            f"Cannot scan authored source directory: {error.filename}"
        ) from error

    for current, directories, files in os.walk(
        resolved_source,
        followlinks=False,
        onerror=fail_walk,
    ):
        current_path = Path(current)
        kept_directories = []
        for name in directories:
            candidate = current_path / name
            if name == "__pycache__" or name.endswith(GENERATED_DIRECTORY_SUFFIXES):
                continue
            if current_path == resolved_source and name != "codex_wsl_rpc":
                raise ValidationError(f"Unsupported additional top-level source input: {candidate}")
            if candidate.is_symlink():
                raise ValidationError(f"Authored source input must not be a symlink: {candidate}")
            if not candidate.is_dir():
                raise ValidationError(f"Unsupported non-directory source entry: {candidate}")
            kept_directories.append(name)
        directories[:] = kept_directories
        for name in files:
            candidate = current_path / name
            _regular_file(candidate, "Authored source input")
            selected.append(candidate)
    return sorted(selected)


def path_fingerprint(path: Path) -> tuple[object, ...] | None:
    """Describe one generated path without following it."""

    if path.is_symlink():
        return ("symlink", os.readlink(path))
    if not path.exists():
        return None
    if path.is_dir():
        entries = tuple(
            (item.name, path_fingerprint(item))
            for item in sorted(path.iterdir(), key=lambda entry: entry.name)
        )
        return ("directory", entries)
    if path.is_file():
        return ("file", path.read_bytes())
    return ("other", "")


def copy_project(workspace: Path, root: Path = ROOT, source: Path = SOURCE_ROOT) -> Path:
    """Copy selected working-tree bytes and verify the copy."""

    project = workspace / "project"
    project.mkdir()
    originals = selected_source_files(root, source)
    for original in originals:
        relative = original.relative_to(root)
        destination = project / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(original.read_bytes())
        if destination.read_bytes() != original.read_bytes():
            raise ValidationError(f"Copied input does not match original: {relative}")
    copied = selected_source_files(project, project / "src")
    copied_relatives = {path.relative_to(project) for path in copied}
    original_relatives = {path.relative_to(root) for path in originals}
    if copied_relatives != original_relatives:
        raise ValidationError("Copied project input set does not match selected source inputs")
    return project


def validate_provisioned_wheel(cache: Path, wheelhouse: Path = PROVISIONED_WHEELHOUSE) -> Path:
    """Return the sole approved externally provisioned wheel."""

    if wheelhouse.is_symlink() or not wheelhouse.is_dir():
        raise ValidationError("Provisioned wheelhouse must be a real directory")
    resolved = wheelhouse.resolve(strict=True)
    if resolved.parent != cache:
        raise ValidationError("Provisioned wheelhouse is outside the repository cache")
    entries = list(resolved.iterdir())
    if len(entries) != 1 or entries[0].name != SETUPTOOLS_WHEEL:
        raise ValidationError(f"Wheelhouse must contain exactly {SETUPTOOLS_WHEEL}")
    wheel = entries[0]
    _regular_file(wheel, "Approved setuptools wheel")
    digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
    if digest != SETUPTOOLS_SHA256:
        raise ValidationError(f"Setuptools wheel SHA-256 mismatch: {digest}")
    return wheel


def controlled_environment(workspace: Path) -> dict[str, str]:
    """Create the single allowlisted environment used by packaging children."""

    temporary = workspace / "tmp"
    home = workspace / "home"
    cache = workspace / "cache"
    data = workspace / "data"
    for directory in (temporary, home, cache, data):
        directory.mkdir()
    return {
        "APPDATA": str(data),
        "HOME": str(home),
        "LOCALAPPDATA": str(data),
        "PATH": os.defpath,
        "PIP_CONFIG_FILE": os.devnull,
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "TEMP": str(temporary),
        "TMP": str(temporary),
        "TMPDIR": str(temporary),
        "USERPROFILE": str(home),
        "XDG_CACHE_HOME": str(cache),
        "XDG_CONFIG_HOME": str(workspace / "config"),
        "XDG_DATA_HOME": str(data),
    }


def run_checked(runner: Runner, arguments: Sequence[str], *, cwd: Path,
                environment: dict[str, str], timeout: int = SUBPROCESS_TIMEOUT_SECONDS
                ) -> subprocess.CompletedProcess[str]:
    """Run one bounded shell-free child and translate failures clearly."""

    try:
        result = runner(
            list(arguments), cwd=cwd, env=environment, capture_output=True,
            text=True, check=False, shell=False, timeout=timeout,
        )
    except subprocess.TimeoutExpired as error:
        raise ValidationError(f"Command timed out after {timeout} seconds: {arguments[0]}") from error
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise ValidationError(f"Command failed ({result.returncode}): {detail}")
    return result


def validate_installation(workspace: Path, project: Path, venv_python: Path,
                          environment: dict[str, str], runner: Runner) -> None:
    """Probe editable metadata and import origin from neither source directory."""

    report = workspace / "installed.json"
    probe_environment = dict(environment)
    probe_environment["FOUNDATION_REPORT"] = str(report)
    probe_environment["FOUNDATION_ALLOWED_READ_ROOTS"] = json.dumps([
        str((project / "src").resolve()),
        str(venv_python.parent.parent.resolve()),
        str(Path(sys.base_prefix).resolve()),
    ])
    run_checked(
        runner, [str(venv_python), "-I", "-B", "-c",
                 guarded_import_probe(
                     include_distribution_metadata=True,
                     include_mock_subpackage=True,
                     include_integration_subpackage=True,
                 )],
        cwd=workspace / "run", environment=probe_environment,
        timeout=PROBE_TIMEOUT_SECONDS,
    )
    observation = json.loads(report.read_text(encoding="utf-8"))
    expected_origin = (project / "src/codex_wsl_rpc/__init__.py").resolve()
    if Path(observation["origin"]) != expected_origin:
        raise ValidationError(f"Installed package origin mismatch: {observation['origin']}")
    expected_mock_origin = (project / "src/codex_wsl_rpc/mock/__init__.py").resolve()
    if Path(observation["mock_origin"]) != expected_mock_origin:
        raise ValidationError(
            f"Installed mock package origin mismatch: {observation['mock_origin']}"
        )
    expected_integration_origin = (project / "src/codex_wsl_rpc/integration/__init__.py").resolve()
    if Path(observation["integration_origin"]) != expected_integration_origin:
        raise ValidationError(
            "Installed integration package origin mismatch: "
            f"{observation['integration_origin']}"
        )
    expected = {
        "name": "codex-wsl-rpc", "version": "0.0.0",
        "requires_python": ">=3.11", "requires_dist": [], "entry_points": [],
    }
    filesystem_violation = any(
        item["write"] or not item["allowed"] for item in observation["filesystem_io"]
    )
    if observation["metadata"] != expected or observation["invoked"] or filesystem_violation:
        raise ValidationError(f"Installed distribution validation failed: {observation}")


def execute(workspace: Path, *, runner: Runner | None = None,
            root: Path = ROOT, wheelhouse: Path = PROVISIONED_WHEELHOUSE) -> None:
    """Execute the complete packaging pipeline in one already-owned workspace."""

    runner = run_process if runner is None else runner
    source = validate_source_root(root, root / "src")
    original_metadata = source / "codex_wsl_rpc.egg-info"
    metadata_before = path_fingerprint(original_metadata)
    cache = repository_cache_dir(root / ".cache", root)
    wheel = validate_provisioned_wheel(cache, wheelhouse)
    environment = controlled_environment(workspace)
    project = copy_project(workspace, root, source)
    private_wheels = workspace / "wheels"
    private_wheels.mkdir()
    private_wheel = private_wheels / SETUPTOOLS_WHEEL
    private_wheel.write_bytes(wheel.read_bytes())
    if hashlib.sha256(private_wheel.read_bytes()).hexdigest() != SETUPTOOLS_SHA256:
        raise ValidationError("Private wheel copy failed digest verification")
    venv = workspace / "venv"
    run = workspace / "run"
    run.mkdir()
    if venv.exists() or venv.is_symlink():
        raise ValidationError("Fresh workspace venv destination is not absent")
    run_checked(runner, [sys.executable, "-m", "venv", str(venv)], cwd=workspace,
                environment=environment)
    venv_python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    run_checked(
        runner,
        [str(venv_python), "-m", "pip", "--isolated", "--disable-pip-version-check",
         "--no-input", "install", "--no-index", "--no-cache-dir", "--no-deps",
         "--find-links", str(private_wheels), "--editable", str(project)],
        cwd=run, environment=environment,
    )
    validate_installation(workspace, project, venv_python, environment, runner)
    # The original source is read-only input; editable metadata belongs to the copy.
    if path_fingerprint(original_metadata) != metadata_before:
        raise ValidationError("Packaging altered metadata in original src")


def main() -> int:
    """Allocate one fresh workspace, validate, and clean only after success."""

    if not sys.platform.startswith("linux"):
        print(
            "PACKAGING VALIDATION FAILED: this command requires Linux/WSL; "
            "use the documented Linux/WSL validation path",
            file=sys.stderr,
        )
        return 1
    try:
        cache = repository_cache_dir(CACHE, ROOT)
        workspace = Path(tempfile.mkdtemp(prefix="packaging-check-", dir=cache))
    except (AssertionError, OSError) as error:
        print(f"PACKAGING VALIDATION FAILED: {error}", file=sys.stderr)
        return 1
    try:
        execute(workspace)
    except (AssertionError, OSError, ValidationError, json.JSONDecodeError) as error:
        print(f"PACKAGING VALIDATION FAILED: {error}", file=sys.stderr)
        print(f"Workspace retained: {workspace.relative_to(ROOT)}", file=sys.stderr)
        return 1
    shutil.rmtree(workspace)
    print("PACKAGING VALIDATION PASSED")
    print(f"Validated fresh workspace: {workspace.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
