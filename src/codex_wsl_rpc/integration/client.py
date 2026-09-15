"""Gated orchestration of initialize and exactly one project/list request."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import os
from pathlib import Path
import stat
import subprocess
import sys
import time
from typing import Callable

from codex_wsl_rpc.protocol import (ClientInfo, ErrorResponse, InitializeCapabilities,
    InitializeParams, InitializeResponse, Notification, ProjectListParams,
    ProjectListResponse, ProjectSortKey, Request, SortDirection, SuccessResponse)
from .transport import _StreamTransport, TransportError

PINNED_CODEX_SHA = "7efa9d96fb34c3cafe108a3c870bfc33e5635772"
INITIALIZE_TIMEOUT = 10.0
PROJECT_LIST_TIMEOUT = 10.0
CLOSE_TIMEOUT = 2.0
TERMINATE_TIMEOUT = 2.0
KILL_TIMEOUT = 2.0

class IntegrationAuthorization(Enum):
    READ_ONLY_PROJECT_LIST = "I understand this starts the exact selected Codex app-server for one read-only project/list page"

class IntegrationError(RuntimeError):
    """Safe base error; messages never include product data or paths."""

class AuthorizationError(IntegrationError): pass
class InvalidTargetError(IntegrationError): pass
class UnsupportedPlatformError(IntegrationError): pass
class UnsupportedTargetError(IntegrationError): pass
class StartupError(IntegrationError): pass
class InitializeError(IntegrationError): pass
class ProjectListError(IntegrationError): pass
class CleanupError(IntegrationError): pass
class OperatorCancelledError(IntegrationError): pass

@dataclass(frozen=True, slots=True)
class ProjectListRunSummary:
    tested_sha: str
    observed_at_utc: str
    target_provenance: str
    version: str
    platform_family: str
    platform_os: str
    initialize_attempted: bool
    initialize_succeeded: bool
    initialized_sent: bool
    project_list_attempted: bool
    project_list_succeeded: bool
    codex_home_category: str
    returned_page_count: int
    has_more: bool
    root_representation_categories: tuple[str, ...]
    cleanup_outcome: str
    mutation_attempted: bool = False
    direct_state_inspection: bool = False
    desktop_comparison_status: str = "NOT_RUN"

    def to_safe_dict(self) -> dict[str, object]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}

@dataclass(frozen=True, slots=True)
class ProjectListRunResult:
    summary: ProjectListRunSummary

def _root_category(path: str) -> str:
    if path.startswith("/"): return "posix_absolute"
    if path.startswith("\\\\"): return "unc_absolute"
    return "windows_drive_absolute"

class ReadOnlyProjectListClient:
    def __init__(self, *, executable_path: Path, home_path: Path,
                 authorization: IntegrationAuthorization,
                 _popen: Callable[..., object] = subprocess.Popen,
                 _clock: Callable[[], float] = time.monotonic) -> None:
        self._executable_path = Path(executable_path)
        self._home_path = Path(home_path)
        self._authorization = authorization
        self._popen = _popen
        self._clock = _clock

    def _validate(self) -> None:
        if self._authorization is not IntegrationAuthorization.READ_ONLY_PROJECT_LIST:
            raise AuthorizationError("explicit read-only authorization is missing")
        if not sys.platform.startswith("linux"):
            raise UnsupportedPlatformError("only Linux/WSL is supported")
        path = self._executable_path
        if not path.is_absolute() or not path.exists():
            raise InvalidTargetError("target must be an existing absolute path")
        try:
            mode = path.lstat().st_mode
            with path.open("rb") as executable:
                header = executable.read(4)
        except OSError as error:
            raise InvalidTargetError("target could not be validated") from error
        if stat.S_ISLNK(mode) or not stat.S_ISREG(mode) or not os.access(path, os.X_OK):
            raise UnsupportedTargetError("target must be a reviewed executable regular file")
        if header != b"\x7fELF":
            raise UnsupportedTargetError("target must be the reviewed concrete native executable")
        if not self._home_path.is_absolute() or not self._home_path.is_dir():
            raise InvalidTargetError("home must be an existing absolute directory")

    def list_one_page(self) -> ProjectListRunResult:
        self._validate()
        process = transport = None
        cleanup = "not_started"
        phase = "startup"
        try:
            try:
                process = self._popen(
                    [str(self._executable_path), "app-server", "--listen", "stdio://"],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    env={"HOME": str(self._home_path), "PATH": os.defpath,
                         "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}, shell=False,
                    bufsize=0, close_fds=True,
                )
            except OSError as error:
                raise StartupError("app-server startup failed") from error
            transport = _StreamTransport(process, clock=self._clock)
            init_deadline = self._clock() + INITIALIZE_TIMEOUT
            params = InitializeParams(ClientInfo("codex-wsl-rpc-read-only", "1"), InitializeCapabilities(experimental_api=True))
            phase = "initialize_send"
            transport.send(Request(1, "initialize", params.to_wire()), init_deadline)
            phase = "initialize_wait"
            response = transport.receive_response(1, init_deadline)
            if isinstance(response, ErrorResponse):
                raise InitializeError("initialize protocol error")
            if not isinstance(response, SuccessResponse):
                raise InitializeError("initialize protocol error")
            try: initialized = InitializeResponse.from_wire(response.result)
            except ValueError as error: raise InitializeError("initialize protocol error") from error
            phase = "initialized_send"
            transport.send(Notification("initialized"), init_deadline)
            list_deadline = self._clock() + PROJECT_LIST_TIMEOUT
            list_params = ProjectListParams(None, 25, ProjectSortKey.POSITION, SortDirection.ASC)
            phase = "project_list_send"
            transport.send(Request(2, "project/list", list_params.to_wire()), list_deadline)
            phase = "project_list_wait"
            response = transport.receive_response(2, list_deadline)
            if isinstance(response, ErrorResponse):
                category = "project store unavailable" if response.error.code == -32601 else "project/list protocol error"
                raise ProjectListError(category)
            if not isinstance(response, SuccessResponse): raise ProjectListError("project/list protocol error")
            try: page = ProjectListResponse.from_wire(response.result)
            except ValueError as error: raise ProjectListError("project/list protocol error") from error
            categories = tuple(sorted({_root_category(root.path) for project in page.data for root in project.roots}))
            phase = "cleanup"
            cleanup = self._cleanup(process, transport)
            process = transport = None
            summary = ProjectListRunSummary(PINNED_CODEX_SHA, datetime.now(timezone.utc).isoformat(),
                "operator_confirmed_pinned_revision", "unobserved", initialized.platform_family,
                initialized.platform_os, True, True, True, True, True,
                "absolute_path_reported_not_exposed", len(page.data), page.next_cursor is not None,
                categories, cleanup)
            return ProjectListRunResult(summary)
        except KeyboardInterrupt as error:
            raise OperatorCancelledError("operator cancelled") from error
        except TransportError as error:
            category = "initialize" if phase in {"initialize_send", "initialize_wait", "initialized_send"} else "project/list"
            raise IntegrationError(f"{category} transport failure") from error
        finally:
            if process is not None:
                self._cleanup(process, transport)

    @staticmethod
    def _cleanup(process, transport) -> str:
        failures = []
        outcome = "graceful"
        if transport is not None:
            try: transport.close()
            except Exception: failures.append("transport")
        try: process.stdin.close()
        except Exception: failures.append("stdin")
        try:
            process.wait(timeout=CLOSE_TIMEOUT)
        except subprocess.TimeoutExpired:
            outcome = "terminated_owned_child"
            try: process.terminate()
            except Exception: failures.append("terminate")
            try: process.wait(timeout=TERMINATE_TIMEOUT)
            except subprocess.TimeoutExpired:
                outcome = "killed_owned_child"
                try: process.kill()
                except Exception: failures.append("kill")
                try: process.wait(timeout=KILL_TIMEOUT)
                except subprocess.TimeoutExpired: failures.append("reap")
                except Exception: failures.append("wait")
            except Exception: failures.append("wait")
        except Exception: failures.append("wait")
        if failures: raise CleanupError("owned-child cleanup failed")
        return outcome
