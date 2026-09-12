"""Small safety helpers shared by source and packaging validation."""

from __future__ import annotations

from pathlib import Path


def repository_cache_dir(cache: Path, root: Path) -> Path:
    """Return the direct, non-symlink ``.cache`` child of *root*."""

    resolved_root = root.resolve(strict=True)
    if cache.is_symlink():
        raise AssertionError("Repository cache path must not be a symbolic link")
    if cache.exists():
        if not cache.is_dir():
            raise AssertionError("Repository cache path exists but is not a directory")
    else:
        if cache.parent.resolve(strict=True) != resolved_root:
            raise AssertionError("Repository cache parent resolves outside the repository root")
        cache.mkdir()
    resolved_cache = cache.resolve(strict=True)
    if resolved_cache.parent != resolved_root:
        raise AssertionError("Repository cache path resolves outside the repository root")
    return resolved_cache


def guarded_import_probe(*, include_distribution_metadata: bool = False) -> str:
    """Return the child-only package probe used by both validation paths."""

    metadata_probe = ""
    if include_distribution_metadata:
        metadata_probe = """
distribution = importlib.metadata.distribution("codex-wsl-rpc")
entry_points = [
    entry.name for entry in distribution.entry_points
    if entry.group in {"console_scripts", "gui_scripts"}
]
metadata_result = {
    "name": distribution.metadata["Name"],
    "version": distribution.version,
    "requires_python": distribution.metadata["Requires-Python"],
    "requires_dist": distribution.requires or [],
    "entry_points": entry_points,
}
"""

    return f"""
import importlib.metadata
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
        raise RuntimeError(f"prohibited primitive invoked: {{name}}")
    return guard

socket.create_connection = prohibited("socket.create_connection")
socket.socket.connect = prohibited("socket.socket.connect")
subprocess.Popen = prohibited("subprocess.Popen")
os.system = prohibited("os.system")
sqlite3.connect = prohibited("sqlite3.connect")

source = os.environ.get("FOUNDATION_SRC")
if source:
    sys.path.insert(0, source)

import codex_wsl_rpc
metadata_result = None
{metadata_probe}
Path(os.environ["FOUNDATION_REPORT"]).write_text(
    json.dumps({{
        "origin": str(Path(codex_wsl_rpc.__file__).resolve()),
        "invoked": invoked,
        "metadata": metadata_result,
    }}),
    encoding="utf-8",
)
"""
