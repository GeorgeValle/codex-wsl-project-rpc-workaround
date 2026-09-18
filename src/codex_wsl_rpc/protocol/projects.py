"""Pure Project and project/list schema models for the pinned protocol."""

from dataclasses import dataclass, field
from enum import StrEnum
import re
from types import MappingProxyType
from typing import Mapping, Self

from ._values import JsonValue, _category, _freeze_json, _validate_i64, _validate_string, _validate_u32
from .errors import ProtocolDecodeError, ProtocolModelError

def _object(value: JsonValue, path: str) -> dict[str, JsonValue]:
    try: _freeze_json(value, path)
    except ProtocolModelError as error: raise ProtocolDecodeError(str(error)) from error
    if not isinstance(value, dict): raise ProtocolDecodeError(f"{path}: expected object; got {_category(value)}")
    return value

def _model(cls: type[Self], **members: object) -> Self:
    try: return cls(**members)
    except (ProtocolModelError, TypeError, ValueError) as error: raise ProtocolDecodeError(str(error)) from error

class ProjectSortKey(StrEnum):
    POSITION = "position"
    RECENCY_AT = "recencyAt"

class SortDirection(StrEnum):
    ASC = "asc"
    DESC = "desc"

@dataclass(frozen=True, slots=True)
class ProjectRoot:
    """A conservatively validated absolute path string (LOCAL MODEL POLICY)."""
    path: str
    def __post_init__(self) -> None:
        _validate_string(self.path, "root.path")
        posix = self.path.startswith("/")
        drive = re.match(r"^[A-Za-z]:[\\/]", self.path) is not None
        unc = re.match(r"^\\\\[^\\/]+[\\/][^\\/]+(?:[\\/].*)?$", self.path) is not None
        if not (posix or drive or unc): raise ProtocolModelError("root.path: expected a clearly absolute path")
    @classmethod
    def from_wire(cls, value: JsonValue) -> Self:
        obj = _object(value, "root")
        if "path" not in obj: raise ProtocolDecodeError("root: missing required member path")
        return _model(cls, path=obj["path"])
    def to_wire(self) -> dict[str, JsonValue]: return {"path": self.path}

@dataclass(frozen=True, slots=True)
class Project:
    id: str
    name: str
    roots: tuple[ProjectRoot, ...]
    metadata: Mapping[str, str]
    position: int
    created_at: int
    updated_at: int
    recency_at: int | None = None
    def __post_init__(self) -> None:
        _validate_string(self.id, "project.id"); _validate_string(self.name, "project.name")
        if not isinstance(self.roots, (tuple, list)): raise ProtocolModelError("project.roots: expected sequence")
        roots = tuple(self.roots)
        if any(not isinstance(root, ProjectRoot) for root in roots): raise ProtocolModelError("project.roots: expected ProjectRoot items")
        object.__setattr__(self, "roots", roots)
        if not isinstance(self.metadata, Mapping): raise ProtocolModelError("project.metadata: expected mapping")
        copied: dict[str, str] = {}
        for key, value in self.metadata.items():
            _validate_string(key, "project.metadata key"); _validate_string(value, f"project.metadata.{key}"); copied[key] = value
        object.__setattr__(self, "metadata", MappingProxyType(copied))
        for name, value in (("position", self.position), ("createdAt", self.created_at), ("updatedAt", self.updated_at)): _validate_i64(value, name)
        if self.recency_at is not None: _validate_i64(self.recency_at, "recencyAt")
    @classmethod
    def from_wire(cls, value: JsonValue) -> Self:
        obj = _object(value, "project"); required = ("id", "name", "roots", "metadata", "position", "createdAt", "updatedAt")
        for key in required:
            if key not in obj: raise ProtocolDecodeError(f"project: missing required member {key}")
        if not isinstance(obj["roots"], list): raise ProtocolDecodeError("project.roots: expected array")
        roots = tuple(ProjectRoot.from_wire(item) for item in obj["roots"])
        return _model(cls, id=obj["id"], name=obj["name"], roots=roots, metadata=obj["metadata"], position=obj["position"], created_at=obj["createdAt"], updated_at=obj["updatedAt"], recency_at=obj.get("recencyAt"))
    def to_wire(self) -> dict[str, JsonValue]:
        return {"id": self.id, "name": self.name, "roots": [root.to_wire() for root in self.roots], "metadata": dict(self.metadata), "position": self.position, "createdAt": self.created_at, "updatedAt": self.updated_at, "recencyAt": self.recency_at}

@dataclass(frozen=True, slots=True)
class ProjectListParams:
    cursor: str | None = None
    limit: int | None = None
    sort_key: ProjectSortKey | None = None
    sort_direction: SortDirection | None = None
    def __post_init__(self) -> None:
        if self.cursor is not None: _validate_string(self.cursor, "cursor")
        if self.limit is not None: _validate_u32(self.limit, "limit")
        for name, value, kind in (("sort_key", self.sort_key, ProjectSortKey), ("sort_direction", self.sort_direction, SortDirection)):
            if value is not None and not isinstance(value, kind): raise ProtocolModelError(f"{name}: expected {kind.__name__}")
    @classmethod
    def from_wire(cls, value: JsonValue) -> Self:
        obj = _object(value, "project/list params")
        try:
            key = None if obj.get("sortKey") is None else ProjectSortKey(obj["sortKey"])
            direction = None if obj.get("sortDirection") is None else SortDirection(obj["sortDirection"])
        except (ValueError, TypeError) as error: raise ProtocolDecodeError("project/list params: invalid enum value") from error
        return _model(cls, cursor=obj.get("cursor"), limit=obj.get("limit"), sort_key=key, sort_direction=direction)
    def to_wire(self) -> dict[str, JsonValue]: return {"cursor": self.cursor, "limit": self.limit, "sortKey": None if self.sort_key is None else self.sort_key.value, "sortDirection": None if self.sort_direction is None else self.sort_direction.value}

@dataclass(frozen=True, slots=True)
class ProjectListResponse:
    data: tuple[Project, ...]
    next_cursor: str | None = None
    def __post_init__(self) -> None:
        if not isinstance(self.data, (tuple, list)): raise ProtocolModelError("data: expected sequence")
        data = tuple(self.data)
        if any(not isinstance(item, Project) for item in data): raise ProtocolModelError("data: expected Project items")
        object.__setattr__(self, "data", data)
        if self.next_cursor is not None: _validate_string(self.next_cursor, "nextCursor")
    @classmethod
    def from_wire(cls, value: JsonValue) -> Self:
        obj = _object(value, "project/list response")
        if "data" not in obj: raise ProtocolDecodeError("project/list response: missing required member data")
        if "nextCursor" not in obj: raise ProtocolDecodeError("project/list response: missing required member nextCursor")
        if not isinstance(obj["data"], list): raise ProtocolDecodeError("data: expected array")
        return _model(cls, data=tuple(Project.from_wire(item) for item in obj["data"]), next_cursor=obj["nextCursor"])
    def to_wire(self) -> dict[str, JsonValue]: return {"data": [item.to_wire() for item in self.data], "nextCursor": self.next_cursor}
