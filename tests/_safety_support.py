"""Small filesystem-safety helpers shared by repository tests."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import stat


ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".cache"
SRC = (ROOT / "src").resolve()
WHEELHOUSE = CACHE / "codex-wsl-rpc-wheelhouse"
PACKAGING_TMP = CACHE / "codex-wsl-rpc-packaging-tmp"
PACKAGING_VENV = CACHE / "codex-wsl-rpc-packaging-venv"
EDITABLE_EGG_INFO = SRC / "codex_wsl_rpc.egg-info"
SETUPTOOLS_WHEEL = "setuptools-84.0.0-py3-none-any.whl"
SETUPTOOLS_SHA256 = (
    "51a52592b3b99e102b609654876bd65f19f999935166d1352678931132b0c670"
)


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
            raise AssertionError("Repository cache path resolves outside the repository root")
        return resolved_cache
    if cache.parent.resolve(strict=True) != resolved_root:
        raise AssertionError("Repository cache parent resolves outside the repository root")
    cache.mkdir()
    if cache.is_symlink():
        raise AssertionError("Repository cache path became a symbolic link")
    resolved_cache = cache.resolve(strict=True)
    if resolved_cache.parent != resolved_root:
        raise AssertionError("Repository cache path resolves outside the repository root")
    return resolved_cache


def repository_disposable_dir(path: Path, cache: Path = CACHE, root: Path = ROOT) -> Path:
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
    if path.parent.resolve(strict=True) != resolved_cache:
        raise AssertionError("Disposable path parent is not the repository cache")
    path.mkdir()
    if path.is_symlink():
        raise AssertionError("Disposable path became a symbolic link")
    resolved_path = path.resolve(strict=True)
    if resolved_path.parent != resolved_cache:
        raise AssertionError("Disposable path resolves outside the repository cache")
    return resolved_path


def prepare_disposable_directory(path: Path, *, remove_existing: bool = False,
                                 cache: Path = CACHE, root: Path = ROOT) -> Path:
    """Ensure the exact packaging-venv directory is absent."""

    resolved_cache = repository_cache_dir(cache=cache, root=root)
    if path.name != PACKAGING_VENV.name:
        raise AssertionError("Disposable path is not the packaging venv")
    if path.is_symlink():
        raise AssertionError("Disposable path must not be a symbolic link")
    if path.parent.resolve(strict=True) != resolved_cache:
        raise AssertionError("Disposable path parent is not the repository cache")
    if path.exists():
        if not path.is_dir():
            raise AssertionError("Disposable path exists but is not a directory")
        resolved_path = path.resolve(strict=True)
        if resolved_path.parent != resolved_cache:
            raise AssertionError("Disposable path resolves outside the repository cache")
        if not remove_existing:
            raise AssertionError("Disposable path must be absent before fresh creation")
        shutil.rmtree(resolved_path)
    if path.exists() or path.is_symlink():
        raise AssertionError("Disposable path was not removed before fresh creation")
    return path


def validate_setuptools_wheelhouse(wheelhouse: Path = WHEELHOUSE,
                                   cache: Path = CACHE, root: Path = ROOT,
                                   expected_sha256: str = SETUPTOOLS_SHA256) -> Path:
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
        raise AssertionError("Setuptools wheelhouse resolves outside the repository cache")
    entries = list(os.scandir(resolved_wheelhouse))
    if len(entries) != 1:
        raise AssertionError("Wheelhouse must contain exactly one approved artifact")
    entry = entries[0]
    if entry.name != SETUPTOOLS_WHEEL:
        raise AssertionError(f"Wheelhouse artifact must be {SETUPTOOLS_WHEEL}; found {entry.name!r}")
    if entry.is_symlink():
        raise AssertionError("Approved wheelhouse artifact must not be a symbolic link")
    if not stat.S_ISREG(entry.stat(follow_symlinks=False).st_mode):
        raise AssertionError("Approved wheelhouse artifact must be a regular file")
    wheel = Path(entry.path).resolve(strict=True)
    if wheel.parent != resolved_wheelhouse:
        raise AssertionError("Approved wheel resolves outside the validated wheelhouse")
    digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
    if digest != expected_sha256:
        raise AssertionError(f"Setuptools wheel SHA-256 mismatch: expected {expected_sha256}, found {digest}")
    return wheel


def require_absent_editable_egg_info(path: Path = EDITABLE_EGG_INFO,
                                     src: Path = SRC) -> Path:
    """Fail closed unless the exact editable-build metadata path is absent."""

    resolved_src = src.resolve(strict=True)
    if path.parent.resolve(strict=True) != resolved_src:
        raise AssertionError("Editable egg-info parent is not the repository src directory")
    if path.is_symlink():
        raise AssertionError("Editable egg-info path must not be a symbolic link")
    if path.exists():
        raise AssertionError("Editable egg-info path must be absent before pip")
    return path


def remove_generated_editable_egg_info(path: Path = EDITABLE_EGG_INFO,
                                       src: Path = SRC) -> None:
    """Validate and remove only the exact generated editable metadata directory."""

    resolved_src = src.resolve(strict=True)
    if path.is_symlink() or not path.is_dir():
        raise AssertionError("Generated editable egg-info must be a real directory")
    resolved_path = path.resolve(strict=True)
    if resolved_path.parent != resolved_src or resolved_path != resolved_src / path.name:
        raise AssertionError("Generated editable egg-info is outside repository src")
    shutil.rmtree(resolved_path)
