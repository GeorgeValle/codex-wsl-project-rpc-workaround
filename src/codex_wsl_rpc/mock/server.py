"""Deterministic fake app-server with only initialize and project/list."""

from __future__ import annotations

from enum import Enum, auto
from functools import cmp_to_key
import uuid

from codex_wsl_rpc.protocol import (
    ErrorResponse, InitializeParams, InitializeResponse, Notification, Project,
    ProjectListParams, ProjectListResponse, ProjectSortKey, ProtocolDecodeError,
    ProtocolError, Request, SortDirection, SuccessResponse,
)

_INVALID_CURSOR = "invalid project cursor: malformed or mismatched sort anchor"
_I64_MIN = -(2**63)
_I64_MAX = 2**63 - 1


class _LifecycleState(Enum):
    UNINITIALIZED = auto()
    INITIALIZED = auto()


class _ProjectStore:
    def __init__(self, projects: tuple[Project, ...] | list[Project]) -> None:
        snapshots = tuple(Project.from_wire(project.to_wire()) for project in projects)
        for project in snapshots:
            if not _canonical_uuid(project.id):
                raise ValueError("mock Project fixture id must be a canonical UUID")
        self._projects = snapshots

    def snapshot(self) -> tuple[Project, ...]:
        return tuple(Project.from_wire(project.to_wire()) for project in self._projects)


def _canonical_uuid(value: str) -> bool:
    try:
        return str(uuid.UUID(value)) == value
    except (ValueError, AttributeError):
        return False


def _effective_order(params: ProjectListParams) -> tuple[ProjectSortKey, SortDirection]:
    if params.sort_key is None:
        if params.sort_direction is not None:
            raise ProtocolDecodeError("sortDirection requires sortKey")
        return ProjectSortKey.POSITION, SortDirection.ASC
    direction = params.sort_direction
    if direction is None:
        direction = SortDirection.ASC if params.sort_key is ProjectSortKey.POSITION else SortDirection.DESC
    return params.sort_key, direction


def _cursor(project: Project, key: ProjectSortKey, direction: SortDirection) -> str:
    if key is ProjectSortKey.POSITION and direction is SortDirection.ASC:
        return f"{project.position}|{project.id}"
    value = project.position if key is ProjectSortKey.POSITION else project.recency_at
    rendered = "null" if value is None else str(value)
    return f"v1|{key.value}|{direction.value}|{rendered}|{project.id}"


def _parse_cursor(cursor: str, key: ProjectSortKey, direction: SortDirection) -> tuple[int | None, str]:
    if len(cursor) > 128:
        raise ProtocolDecodeError(_INVALID_CURSOR)
    parts = cursor.split("|")
    if len(parts) == 2 and key is ProjectSortKey.POSITION and direction is SortDirection.ASC:
        value_text, project_id = parts
    elif len(parts) == 5 and parts[:3] == ["v1", key.value, direction.value]:
        value_text, project_id = parts[3:]
    else:
        raise ProtocolDecodeError(_INVALID_CURSOR)
    if value_text == "null" and key is ProjectSortKey.RECENCY_AT:
        value = None
    else:
        try:
            value = int(value_text)
        except ValueError as error:
            raise ProtocolDecodeError(_INVALID_CURSOR) from error
        if str(value) != value_text or (
            key is ProjectSortKey.POSITION and not _I64_MIN <= value <= _I64_MAX
        ):
            raise ProtocolDecodeError(_INVALID_CURSOR)
    if not _canonical_uuid(project_id):
        raise ProtocolDecodeError(_INVALID_CURSOR)
    return value, project_id


def _compare_values(left_value: int | None, left_id: str, right_value: int | None,
                    right_id: str, key: ProjectSortKey, direction: SortDirection) -> int:
    if key is ProjectSortKey.RECENCY_AT and (left_value is None or right_value is None):
        if left_value is None and right_value is not None:
            return 1
        if left_value is not None and right_value is None:
            return -1
    sign = 1 if direction is SortDirection.ASC else -1
    if left_value != right_value:
        assert left_value is not None and right_value is not None
        return sign * (-1 if left_value < right_value else 1)
    if left_id == right_id:
        return 0
    return sign * (-1 if left_id < right_id else 1)


def _project_value(project: Project, key: ProjectSortKey) -> int | None:
    return project.position if key is ProjectSortKey.POSITION else project.recency_at


class FakeAppServer:
    """A fresh explicit lifecycle plus an immutable synthetic Project snapshot."""

    def __init__(self, projects: tuple[Project, ...] | list[Project] = ()) -> None:
        self._store = _ProjectStore(projects)
        self._lifecycle = _LifecycleState.UNINITIALIZED
        self._experimental_enabled = False

    def handle(self, envelope: Request | Notification) -> SuccessResponse | ErrorResponse | None:
        if isinstance(envelope, Notification):
            # Pinned message_processor.rs logs all client notifications and does not
            # use `initialized` as a lifecycle or capability transition.
            return None
        try:
            if envelope.method == "initialize":
                return self._handle_initialize(envelope)
            if self._lifecycle is _LifecycleState.UNINITIALIZED:
                return self._error_response(envelope, -32600, "Not initialized")
            if envelope.method == "project/list":
                return self._handle_project_list(envelope)
            # The pinned revision establishes the generic code, but not wording for
            # this mock dispatch boundary. Keep the local wording deterministic.
            return self._error_response(envelope, -32601, "Method not found")
        except ProtocolDecodeError as error:
            return self._error_response(envelope, -32602, str(error))
        except Exception:
            return self._error_response(envelope, -32603, "Internal mock server error")

    def _handle_initialize(self, request: Request) -> SuccessResponse | ErrorResponse:
        if self._lifecycle is _LifecycleState.INITIALIZED:
            return self._error_response(request, -32600, "Already initialized")
        params = InitializeParams.from_wire(request.params)
        self._experimental_enabled = bool(
            params.capabilities is not None and params.capabilities.experimental_api
        )
        self._lifecycle = _LifecycleState.INITIALIZED
        result = InitializeResponse(
            "codex-wsl-rpc-mock/1", "/mock/codex-home", "mock", "mock"
        )
        return SuccessResponse(request.id, result.to_wire())

    def _handle_project_list(self, request: Request) -> SuccessResponse | ErrorResponse:
        if not self._experimental_enabled:
            return self._error_response(
                request, -32600, "project/list requires experimentalApi capability"
            )
        params = ProjectListParams.from_wire(request.params)
        key, direction = _effective_order(params)
        anchor = None if params.cursor is None else _parse_cursor(params.cursor, key, direction)
        projects = list(self._store.snapshot())
        projects.sort(key=cmp_to_key(lambda left, right: _compare_values(
            _project_value(left, key), left.id, _project_value(right, key), right.id,
            key, direction,
        )))
        if anchor is not None:
            projects = [project for project in projects if _compare_values(
                _project_value(project, key), project.id, anchor[0], anchor[1], key, direction,
            ) > 0]
        limit = 25 if params.limit is None else max(1, min(params.limit, 100))
        has_more = len(projects) > limit
        page = projects[:limit]
        next_cursor = _cursor(page[-1], key, direction) if has_more else None
        result = ProjectListResponse(tuple(page), next_cursor)
        return SuccessResponse(request.id, result.to_wire())

    @staticmethod
    def _error_response(request: Request, code: int, message: str) -> ErrorResponse:
        return ErrorResponse(request.id, ProtocolError(code, message))
