"""Small safety helpers shared by source and packaging validation."""

from __future__ import annotations

from pathlib import Path


# Import machinery may enumerate package directories.  Other ``os.*`` audit
# events are not required by the supported import paths and are denied.
READ_ONLY_OS_AUDIT_EVENTS = frozenset({"os.listdir", "os.scandir"})

# CPython does not audit every mutator consistently.  Patch this small set of
# standard-library fallbacks when present; pathlib delegates to these APIs.
FILESYSTEM_MUTATION_PRIMITIVES = (
    "unlink", "remove", "rename", "replace", "rmdir", "mkdir", "makedirs",
    "link", "symlink", "truncate", "chmod", "chown", "utime", "setxattr",
    "removexattr",
)


def is_denied_import_audit_event(event: str) -> bool:
    """Return whether an audit event is categorically forbidden on import."""

    return (
        event.startswith("socket.")
        or (event.startswith("os.") and event not in READ_ONLY_OS_AUDIT_EVENTS)
    )


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
import encodings.idna
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

allowed_read_roots = [
    Path(value).resolve()
    for value in json.loads(os.environ["FOUNDATION_ALLOWED_READ_ROOTS"])
]
filesystem_io = []
denied_audit_events = []
observing_import = True

READ_ONLY_OS_AUDIT_EVENTS = frozenset({READ_ONLY_OS_AUDIT_EVENTS!r})
FILESYSTEM_MUTATION_PRIMITIVES = {FILESYSTEM_MUTATION_PRIMITIVES!r}

for primitive in FILESYSTEM_MUTATION_PRIMITIVES:
    if hasattr(os, primitive):
        setattr(os, primitive, prohibited("os." + primitive))

def observe_import_activity(event, arguments):
    if not observing_import:
        return
    if event.startswith("socket.") or (
        event.startswith("os.") and event not in READ_ONLY_OS_AUDIT_EVENTS
    ):
        denied_audit_events.append(event)
        raise RuntimeError(f"prohibited audit event: {{event}}")
    if event != "open":
        return
    raw_path, mode, flags = arguments
    if isinstance(raw_path, int):
        path = f"file-descriptor:{{raw_path}}"
        allowed = False
    else:
        candidate = Path(raw_path)
        if not candidate.is_absolute():
            candidate = Path.cwd() / candidate
        resolved = candidate.resolve()
        path = str(resolved)
        allowed = any(resolved == root or root in resolved.parents for root in allowed_read_roots)
    writing = (
        isinstance(mode, str) and any(marker in mode for marker in "wax+")
    ) or (
        isinstance(flags, int)
        and bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
    )
    filesystem_io.append({{"path": path, "write": writing, "allowed": allowed}})
    if writing or not allowed:
        raise RuntimeError(f"prohibited filesystem open: {{path}}")

sys.addaudithook(observe_import_activity)
import codex_wsl_rpc
observing_import = False
metadata_result = None
{metadata_probe}
Path(os.environ["FOUNDATION_REPORT"]).write_text(
    json.dumps({{
        "origin": str(Path(codex_wsl_rpc.__file__).resolve()),
        "invoked": invoked,
        "filesystem_io": filesystem_io,
        "denied_audit_events": denied_audit_events,
        "metadata": metadata_result,
    }}),
    encoding="utf-8",
)
if any(item["write"] or not item["allowed"] for item in filesystem_io):
    raise RuntimeError("prohibited filesystem I/O observed during package import")
if denied_audit_events:
    raise RuntimeError("prohibited audit event observed during package import")
if invoked:
    raise RuntimeError("prohibited primitive observed during package import")
"""
