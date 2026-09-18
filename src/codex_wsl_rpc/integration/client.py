"""Gated orchestration of initialize and exactly one project/list request."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import os
from pathlib import Path
import re
import secrets
import signal
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
CLEANUP_TOTAL_TIMEOUT = CLOSE_TIMEOUT + TERMINATE_TIMEOUT + KILL_TIMEOUT
MAX_MASK_ACQUISITION_ATTEMPTS = 4

class IntegrationAuthorization(Enum):
    READ_ONLY_PROJECT_LIST = (
        "I confirm I selected the intended already-installed OpenAI Codex executable; "
        "repository code validates only its executable form before one read-only project/list page"
    )

class IntegrationError(RuntimeError):
    """Safe base error with an explicitly operator-safe machine category."""
    category = "integration_failure"

    def __init__(self, message: str, *, category: str | None = None) -> None:
        super().__init__(message)
        self.category = category or type(self).category

class AuthorizationError(IntegrationError): category = "authorization_required"
class InvalidTargetError(IntegrationError): category = "invalid_target"
class UnsupportedPlatformError(IntegrationError): category = "unsupported_platform"
class UnsupportedTargetError(IntegrationError): category = "unsupported_target"
class StartupError(IntegrationError): category = "startup_failure"
class InitializeError(IntegrationError): category = "initialize_protocol_error"
class ProjectListError(IntegrationError): category = "project_list_protocol_error"
class CleanupError(IntegrationError): category = "cleanup_failure"
class OperatorCancelledError(IntegrationError): category = "operator_cancelled"

@dataclass(frozen=True, slots=True)
class ProjectListRunSummary:
    protocol_reference_sha: str
    observed_at_utc: str
    target_provenance: str
    target_revision_mapping: str
    target_version: str
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
    product_state_impact: str = "NOT_ESTABLISHED"
    network_effects: str = "NOT_ESTABLISHED"
    helper_process_effects: str = "NOT_ESTABLISHED"

    def to_safe_dict(self) -> dict[str, object]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}

@dataclass(frozen=True, slots=True)
class ProjectListRunResult:
    summary: ProjectListRunSummary

class _SignalDelivery(Enum):
    NOT_ATTEMPTED = "not_attempted"
    DELIVERY_UNCERTAIN = "delivery_uncertain"
    DELIVERED = "delivered"


def _reconcile_terminal_status(
        returncode: int,
        terminate_state: _SignalDelivery,
        kill_state: _SignalDelivery) -> str | None:
    """Return a truthful cleanup outcome for a compatible terminal history."""
    if returncode == 0:
        if kill_state is _SignalDelivery.DELIVERED:
            return "killed_owned_child"
        if terminate_state is _SignalDelivery.DELIVERED:
            return "terminated_owned_child"
        return "graceful"

    if (returncode == -signal.SIGKILL and
            kill_state is _SignalDelivery.DELIVERED):
        return "killed_owned_child"
    if (returncode == -signal.SIGTERM and
            terminate_state is _SignalDelivery.DELIVERED):
        return "terminated_owned_child"
    return None

@dataclass(slots=True)
class _OwnedChildCleanup:
    process: object | None
    transport: object | None
    started: bool = False
    completed: bool = False
    terminate_state: _SignalDelivery = _SignalDelivery.NOT_ATTEMPTED
    kill_state: _SignalDelivery = _SignalDelivery.NOT_ATTEMPTED
    terminate_attempts: int = 0
    kill_attempts: int = 0
    interrupted: bool = False
    protection_failed: bool = False

@dataclass(slots=True)
class _ValidatedTarget:
    """Caller-owned validation resources, created before validation begins."""
    executable_fd: int | None = None
    home_fd: int | None = None

    def release(self) -> list[str]:
        """Relinquish each descriptor before its fallible, non-retryable close."""
        failures: list[str] = []
        for name in ("home_fd", "executable_fd"):
            fd = getattr(self, name)
            setattr(self, name, None)
            if fd is None:
                continue
            try:
                os.close(fd)
            except (OSError, KeyboardInterrupt):
                # close(2) may have succeeded before Python observed failure.
                # Retrying the numeric fd could close an unrelated reused fd.
                failures.append(name)
        return failures

    def close(self) -> None:
        """Compatibility shim for tests; release remains take-before-close."""
        if self.release():
            raise CleanupError("validation descriptor release failed")


@dataclass(slots=True)
class _IntegrationLifecycle:
    """Private owner for this integration's mandatory finalization work."""
    target: _ValidatedTarget
    child: _OwnedChildCleanup | None = None
    transport: object | None = None
    deferred_cancellation: bool = False
    primary_failure: BaseException | None = None
    finalization_failures: list[str] | None = None

    def finalize(self, cleanup: Callable[[_OwnedChildCleanup], str]) -> str | None:
        failures = self.finalization_failures = []
        outcome = None
        # Child safety is independent of auxiliary descriptor release.
        if (self.child is not None and not self.child.started and
                not self.child.protection_failed):
            try:
                outcome = cleanup(self.child)
            except OperatorCancelledError:
                self.deferred_cancellation = True
            except CleanupError:
                failures.append("child")
        failures.extend(self.target.release())
        if failures:
            raise CleanupError("integration finalization failed")
        if self.deferred_cancellation:
            raise OperatorCancelledError("operator cancelled")
        return outcome

def _path_category(path: str) -> str:
    if not path: return "empty"
    if path.startswith("\\\\"): return "unc_absolute"
    if path.startswith("/"): return "posix_absolute"
    drive = path[0] if path else ""
    if ("A" <= drive <= "Z" or "a" <= drive <= "z") and len(path) >= 3 and path[1] == ":" and path[2] in "/\\":
        return "windows_drive_absolute"
    return "relative"

def _platform_family_category(value: str) -> str:
    """Reduce server-controlled platform-family text to reviewed tokens."""
    return value if value in {"unix", "windows"} else "unknown"

def _platform_os_category(value: str) -> str:
    """Reduce server-controlled platform-OS text to reviewed tokens."""
    return value if value in {"linux", "windows"} else "unknown"

_WSL_KERNEL_RELEASE = re.compile(
    r"^[0-9]+(?:\.[0-9]+)+(?:-[0-9]+)?-"
    r"(?:microsoft(?:-standard(?:-wsl2?)?)?|wsl2?)$",
    re.ASCII | re.IGNORECASE,
)

def _is_wsl_kernel_release(release: str) -> bool:
    """Accept only reviewed WSL forms in a single kernel release field."""
    release = release.removesuffix("\n")
    if not release or release != release.strip():
        return False
    return _WSL_KERNEL_RELEASE.fullmatch(release) is not None

class ReadOnlyProjectListClient:
    def __init__(self, *, executable_path: Path, home_path: Path,
                 authorization: IntegrationAuthorization,
                 _popen: Callable[..., object] = subprocess.Popen,
                 _clock: Callable[[], float] = time.monotonic,
                 _platform: str | None = None,
                 _proc_reader: Callable[[Path], str] = Path.read_text,
                 _lstat: Callable[[Path], os.stat_result] = os.lstat,
                 _id_generator: Callable[[], str] = lambda: secrets.token_hex(16),
                 _sigmask: Callable[..., object] | None = None) -> None:
        self._executable_path = Path(executable_path)
        self._home_path = Path(home_path)
        self._authorization = authorization
        self._popen = _popen
        self._clock = _clock
        self._platform = sys.platform if _platform is None else _platform
        self._proc_reader = _proc_reader
        self._lstat = _lstat
        self._id_generator = _id_generator
        self._sigmask = _sigmask

    def _is_wsl(self) -> bool:
        if not self._platform.startswith("linux"):
            return False
        try:
            release = self._proc_reader(Path("/proc/sys/kernel/osrelease"))
        except (OSError, UnicodeError):
            return False
        return _is_wsl_kernel_release(release)

    def _validate(self, target: _ValidatedTarget) -> None:
        try:
            if self._authorization is not IntegrationAuthorization.READ_ONLY_PROJECT_LIST:
                raise AuthorizationError("explicit read-only authorization is missing")
            if not self._is_wsl():
                raise UnsupportedPlatformError("positive WSL evidence is required")
            path = self._executable_path
            if not path.is_absolute():
                raise InvalidTargetError("target must be an existing absolute path")
            flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) |
                 getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
            try:
                path_status = self._lstat(path)
            except OSError:
                raise InvalidTargetError("target could not be validated") from None
            if not stat.S_ISREG(path_status.st_mode):
                raise UnsupportedTargetError(
                    "target must be a reviewed executable regular file"
                )
            try:
                target.executable_fd = os.open(path, flags)
                opened_status = os.fstat(target.executable_fd)
            except OSError as error:
                raise InvalidTargetError("target could not be validated") from error
            if (stat.S_ISLNK(path_status.st_mode) or
                not stat.S_ISREG(opened_status.st_mode) or
                not opened_status.st_mode & 0o111):
                raise UnsupportedTargetError("target must be a reviewed executable regular file")
            if ((path_status.st_dev, path_status.st_ino) !=
                (opened_status.st_dev, opened_status.st_ino)):
                raise InvalidTargetError("target identity changed during validation")
            try:
                header = os.pread(target.executable_fd, 4, 0)
            except OSError as error:
                raise InvalidTargetError("target could not be validated") from error
            if header != b"\x7fELF":
                raise UnsupportedTargetError("target must be the reviewed concrete native executable")
            self._validate_home(target)
        except (Exception, KeyboardInterrupt):
            target.release()
            raise

    def _validate_home(self, target: _ValidatedTarget) -> None:
        if not self._home_path.is_absolute():
            raise InvalidTargetError("home must be an existing absolute directory")
        flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) |
                 getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_DIRECTORY", 0))
        try:
            path_status = self._lstat(self._home_path)
            if stat.S_ISLNK(path_status.st_mode) or not stat.S_ISDIR(path_status.st_mode):
                raise InvalidTargetError("home must be an existing absolute directory")
            target.home_fd = os.open(self._home_path, flags)
            opened_status = os.fstat(target.home_fd)
            if (not stat.S_ISDIR(opened_status.st_mode) or
                    (path_status.st_dev, path_status.st_ino) !=
                    (opened_status.st_dev, opened_status.st_ino)):
                raise InvalidTargetError("home identity changed during validation")
        except Exception as error:
            if isinstance(error, InvalidTargetError):
                raise
            raise InvalidTargetError("home could not be validated") from error

    def _next_request_id(self, used: set[str]) -> str:
        request_id = self._id_generator()
        if not isinstance(request_id, str) or not request_id or request_id in used:
            raise IntegrationError("request id generation failed")
        used.add(request_id)
        return request_id

    def _resolve_sigmask(self) -> Callable[..., object]:
        sigmask = self._sigmask
        if sigmask is None:
            sigmask = getattr(signal, "pthread_sigmask", None)
        if sigmask is None:
            raise UnsupportedPlatformError("SIGINT masking is unavailable")
        self._sigmask = sigmask
        return sigmask

    def list_one_page(self) -> ProjectListRunResult:
        target = _ValidatedTarget()
        lifecycle = _IntegrationLifecycle(target)
        process = transport = None
        owned_child = None
        cleanup = "not_started"
        phase = "startup"
        request_ids: set[str] = set()
        try:
            self._validate(target)
            assert target.executable_fd is not None and target.home_fd is not None
            sigmask = self._resolve_sigmask()
            try:
                previous_mask = sigmask(signal.SIG_BLOCK, {signal.SIGINT})
                try:
                    process = self._popen(
                    [f"/proc/self/fd/{target.executable_fd}", "app-server", "--listen", "stdio://"],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    env={"HOME": f"/proc/self/fd/{target.home_fd}", "PATH": os.defpath,
                         "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}, shell=False,
                    bufsize=0, close_fds=True,
                    pass_fds=(target.executable_fd, target.home_fd),
                    )
                    owned_child = _OwnedChildCleanup(process, None)
                    lifecycle.child = owned_child
                finally:
                    sigmask(signal.SIG_SETMASK, previous_mask)
            except OSError as error:
                raise StartupError("app-server startup failed") from error
            finally:
                release_failures = target.release()
                if release_failures:
                    raise CleanupError("validation descriptor release failed")
            # Popen transfers ownership of this exact child immediately.  Keep
            # that ownership even if transport initialization only partially
            # succeeds and raises.
            try:
                transport = _StreamTransport(process, clock=self._clock)
            except Exception as error:
                raise StartupError("transport initialization failed") from error
            owned_child.transport = transport
            lifecycle.transport = transport
            init_deadline = self._clock() + INITIALIZE_TIMEOUT
            params = InitializeParams(ClientInfo("codex-wsl-rpc-read-only", "1"), InitializeCapabilities(experimental_api=True))
            initialize_id = self._next_request_id(request_ids)
            phase = "initialize_send"
            transport.send(Request(initialize_id, "initialize", params.to_wire()), init_deadline)
            phase = "initialize_wait"
            response = transport.receive_response(initialize_id, init_deadline)
            if isinstance(response, ErrorResponse):
                raise InitializeError("initialize protocol error")
            if not isinstance(response, SuccessResponse):
                raise InitializeError("initialize protocol error")
            try:
                self._validate_initialize_result(response.result)
                initialized = InitializeResponse.from_wire(response.result)
            except ValueError as error: raise InitializeError("initialize protocol error") from error
            phase = "initialized_send"
            transport.send(Notification("initialized"), init_deadline)
            list_deadline = self._clock() + PROJECT_LIST_TIMEOUT
            list_params = ProjectListParams(None, 25, ProjectSortKey.POSITION, SortDirection.ASC)
            project_list_id = self._next_request_id(request_ids)
            phase = "project_list_send"
            transport.send(Request(project_list_id, "project/list", list_params.to_wire()), list_deadline)
            phase = "project_list_wait"
            response = transport.receive_response(project_list_id, list_deadline)
            if isinstance(response, ErrorResponse):
                category = "project/list unavailable or unsupported" if response.error.code == -32601 else "project/list protocol error"
                safe_code = "project_list_unavailable" if response.error.code == -32601 else None
                raise ProjectListError(category, category=safe_code)
            if not isinstance(response, SuccessResponse): raise ProjectListError("project/list protocol error")
            try:
                self._validate_project_list_result(response.result)
                page = ProjectListResponse.from_wire(response.result)
            except ValueError as error: raise ProjectListError("project/list protocol error") from error
            categories = tuple(sorted({_path_category(root.path) for project in page.data for root in project.roots}))
            phase = "cleanup"
            cleanup = self._cleanup(owned_child)
            if transport.terminal_error is not None:
                raise transport.terminal_error
            process = transport = None
            summary = ProjectListRunSummary(PINNED_CODEX_SHA, datetime.now(timezone.utc).isoformat(),
                "operator_confirmed_openai_codex_unverified_by_repository", "NOT_ESTABLISHED",
                "unobserved", _platform_family_category(initialized.platform_family),
                _platform_os_category(initialized.platform_os), True, True, True, True, True,
                _path_category(initialized.codex_home), len(page.data), page.next_cursor is not None,
                categories, cleanup)
            return ProjectListRunResult(summary)
        except KeyboardInterrupt as error:
            lifecycle.deferred_cancellation = True
            raise OperatorCancelledError("operator cancelled") from error
        except TransportError as error:
            category = "initialize" if phase in {"initialize_send", "initialize_wait", "initialized_send"} else "project/list"
            raise IntegrationError(
                f"{category} transport failure",
                category=f"{category.replace('/', '_')}_transport_failure",
            ) from error
        finally:
            lifecycle.finalize(self._cleanup)

    def _cleanup(self, owned_child: _OwnedChildCleanup) -> str:
        """Finish one bounded cleanup lifecycle, deferring Ctrl+C until reap."""
        try:
            sigmask = self._resolve_sigmask()
        except UnsupportedPlatformError as error:
            owned_child.protection_failed = True
            raise CleanupError("owned-child cleanup protection failed") from error
        deferred_during_mask = False
        cleanup_deadline = None
        for _ in range(MAX_MASK_ACQUISITION_ATTEMPTS):
            try:
                cleanup_deadline = self._clock() + CLEANUP_TOTAL_TIMEOUT
                break
            except KeyboardInterrupt:
                deferred_during_mask = True
        if cleanup_deadline is None:
            owned_child.protection_failed = True
            raise CleanupError("owned-child cleanup protection failed")
        previous_mask = None
        for _ in range(MAX_MASK_ACQUISITION_ATTEMPTS):
            try:
                if self._clock() >= cleanup_deadline:
                    break
                previous_mask = sigmask(signal.SIG_BLOCK, {signal.SIGINT})
                break
            except KeyboardInterrupt:
                # Mask acquisition is part of cleanup entry: cancellation here
                # is deferred, ownership remains intact, and acquisition is
                # retried before the lifecycle is marked as started.
                deferred_during_mask = True
            except Exception as error:
                owned_child.protection_failed = True
                raise CleanupError("owned-child cleanup protection failed") from error
        if previous_mask is None:
            owned_child.protection_failed = True
            raise CleanupError("owned-child cleanup protection failed")
        if deferred_during_mask:
            owned_child.interrupted = True
        terminal_error: CleanupError | None = None
        outcome = "graceful"
        try:
            if owned_child.started:
                if owned_child.completed:
                    raise CleanupError("owned-child cleanup already completed")
                raise CleanupError("owned-child cleanup already attempted")
            owned_child.started = True
            process, transport = owned_child.process, owned_child.transport
            failures: list[str] = []
            outcome, state, deadline = "graceful", "transport_close", None
            stage_timeout = CLOSE_TIMEOUT
            reaped = False
            stdout_eof = getattr(transport, "_supports_terminal_drain", False) is not True

        # SIGINT stays blocked across every state transition.  The local catch
        # remains only for deterministic injected exceptions in tests; real
        # terminal cancellation cannot interrupt its own bookkeeping.
            while state != "terminal":
                try:
                    if state == "transport_close":
                        state = "stdin_close"
                        if (transport is not None and
                                getattr(transport, "_supports_terminal_drain", False) is not True):
                            try: transport.close()
                            except Exception: failures.append("transport")
                    elif state == "stdin_close":
                        state = "deadline"
                        try: process.stdin.close()
                        except Exception: failures.append("stdin")
                    elif state == "deadline":
                        deadline = min(cleanup_deadline, self._clock() + stage_timeout)
                        state = "wait"
                    elif state == "wait":
                        remaining = deadline - self._clock()
                        if remaining <= 0:
                            if getattr(transport, "_supports_terminal_drain", False) is True:
                                child_reaped, stdout_eof = transport.drain_terminal(
                                    process, deadline
                                )
                                reaped = child_reaped and stdout_eof
                                if child_reaped and not stdout_eof:
                                    failures.append("stdout_eof")
                                    state = "finalize"
                                    continue
                            else:
                                reaped = process.returncode is not None
                        else:
                            try:
                                if getattr(transport, "_supports_terminal_drain", False) is True:
                                    child_reaped, stdout_eof = transport.drain_terminal(process, deadline)
                                    reaped = child_reaped and stdout_eof
                                    if child_reaped and not stdout_eof:
                                        if self._clock() >= cleanup_deadline:
                                            failures.append("stdout_eof")
                                            state = "finalize"
                                        else:
                                            deadline = cleanup_deadline
                                            state = "wait"
                                        continue
                                else:
                                    process.wait(timeout=remaining)
                                    reaped = True
                            except subprocess.TimeoutExpired:
                                reaped = False
                            except Exception:
                                failures.append("wait")
                                child_reaped = process.returncode is not None
                                reaped = child_reaped and stdout_eof
                        if reaped:
                            state = "finalize"
                        elif (owned_child.terminate_state is not _SignalDelivery.DELIVERED and
                              owned_child.terminate_attempts < 2):
                            outcome, state = "terminated_owned_child", "terminate"
                        elif (owned_child.kill_state is not _SignalDelivery.DELIVERED and
                              owned_child.kill_attempts < 2):
                            outcome, state = "killed_owned_child", "kill"
                        else:
                            failures.append("reap")
                            state = "finalize"
                    elif state == "terminate":
                        owned_child.terminate_attempts += 1
                        owned_child.terminate_state = _SignalDelivery.DELIVERY_UNCERTAIN
                        state = "terminate_deadline"
                        try:
                            process.terminate()
                            owned_child.terminate_state = _SignalDelivery.DELIVERED
                        except KeyboardInterrupt:
                            owned_child.interrupted = True
                        except Exception: failures.append("terminate")
                    elif state == "terminate_deadline":
                        stage_timeout, state = TERMINATE_TIMEOUT, "deadline"
                    elif state == "kill":
                        owned_child.kill_attempts += 1
                        owned_child.kill_state = _SignalDelivery.DELIVERY_UNCERTAIN
                        state = "kill_deadline"
                        try:
                            process.kill()
                            owned_child.kill_state = _SignalDelivery.DELIVERED
                        except KeyboardInterrupt:
                            owned_child.interrupted = True
                        except Exception: failures.append("kill")
                    elif state == "kill_deadline":
                        stage_timeout, state = KILL_TIMEOUT, "deadline"
                    elif state == "finalize":
                        if reaped and stdout_eof:
                            reconciled = _reconcile_terminal_status(
                                process.returncode,
                                owned_child.terminate_state,
                                owned_child.kill_state,
                            )
                            if reconciled is None:
                                failures.append("child_exit")
                            else:
                                outcome = reconciled
                            owned_child.completed = True
                            owned_child.process = None
                            owned_child.transport = None
                        if getattr(transport, "_supports_terminal_drain", False) is True:
                            try:
                                transport.close()
                            except Exception:
                                failures.append("transport")
                        state = "terminal"
                except KeyboardInterrupt:
                    owned_child.interrupted = True
            if failures:
                terminal_error = CleanupError("owned-child cleanup failed")
        finally:
            try:
                sigmask(signal.SIG_SETMASK, previous_mask)
            except KeyboardInterrupt:
                owned_child.interrupted = True
            except Exception:
                terminal_error = CleanupError("owned-child cleanup protection failed")
        if terminal_error is not None:
            raise terminal_error
        if owned_child.interrupted:
            raise OperatorCancelledError("operator cancelled")
        return outcome

    @staticmethod
    def _validate_initialize_result(value: object) -> None:
        if not isinstance(value, dict) or any(
                key not in value for key in
                ("userAgent", "codexHome", "platformFamily", "platformOs")):
            raise ValueError("invalid initialize shape")

    @staticmethod
    def _validate_project_list_result(value: object) -> None:
        if not isinstance(value, dict) or any(key not in value for key in ("data", "nextCursor")):
            raise ValueError("invalid project/list shape")
        data = value["data"]
        if not isinstance(data, list):
            raise ValueError("invalid project/list shape")
        project_members = ("id", "name", "roots", "metadata", "position",
                           "createdAt", "updatedAt", "recencyAt")
        for project in data:
            if not isinstance(project, dict) or any(key not in project for key in project_members):
                raise ValueError("invalid project/list shape")
            roots = project["roots"]
            if not isinstance(roots, list):
                raise ValueError("invalid project/list shape")
            for root in roots:
                if not isinstance(root, dict) or "path" not in root:
                    raise ValueError("invalid project/list shape")
