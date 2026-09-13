"""Pure value models for the pinned app-server wire envelopes.

The pinned Rust structs use serde's default unknown-member behavior, so ordinary
extra members are ignored while decoding.  ``jsonrpc`` is deliberately rejected:
the pinned protocol explicitly neither sends nor expects that member.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import TypeAlias

from .errors import ProtocolDecodeError, ProtocolModelError


JsonScalar: TypeAlias = None | bool | int | float | str
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
RequestId: TypeAlias = str | int

_I64_MIN = -(2**63)
_I64_MAX = 2**63 - 1


def _category(value: object) -> str:
    return type(value).__name__


def _validate_i64(value: object, path: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ProtocolModelError(f"{path}: expected a signed 64-bit integer; got {_category(value)}")
    if not _I64_MIN <= value <= _I64_MAX:
        raise ProtocolModelError(f"{path}: signed 64-bit integer is out of range")


def _validate_request_id(value: object, path: str = "id") -> None:
    if isinstance(value, str):
        return
    _validate_i64(value, path)


def _validate_string(value: object, path: str) -> None:
    if not isinstance(value, str):
        raise ProtocolModelError(f"{path}: expected string; got {_category(value)}")


def _validate_json(value: object, path: str) -> None:
    if value is None or isinstance(value, (bool, str)):
        return
    if isinstance(value, int):
        return
    if isinstance(value, float):
        if math.isfinite(value):
            return
        raise ProtocolModelError(f"{path}: expected a finite JSON number")
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_json(item, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ProtocolModelError(f"{path}: expected object keys to be strings")
            _validate_json(item, f"{path}.{key}")
        return
    raise ProtocolModelError(f"{path}: expected a JSON-compatible value; got {_category(value)}")


@dataclass(frozen=True, slots=True)
class ProtocolError:
    """The error value nested inside an error response."""

    code: int
    message: str
    data: JsonValue | None = None

    def __post_init__(self) -> None:
        _validate_i64(self.code, "error.code")
        _validate_string(self.message, "error.message")
        if self.data is not None:
            _validate_json(self.data, "error.data")

    def to_wire(self) -> dict[str, JsonValue]:
        wire: dict[str, JsonValue] = {"code": self.code, "message": self.message}
        if self.data is not None:
            wire["data"] = self.data
        return wire


@dataclass(frozen=True, slots=True)
class Request:
    id: RequestId
    method: str
    params: JsonValue | None = None
    trace: JsonValue | None = None

    def __post_init__(self) -> None:
        _validate_request_id(self.id)
        _validate_string(self.method, "method")
        if self.params is not None:
            _validate_json(self.params, "params")
        if self.trace is not None:
            _validate_json(self.trace, "trace")

    def to_wire(self) -> dict[str, JsonValue]:
        wire: dict[str, JsonValue] = {"id": self.id, "method": self.method}
        if self.params is not None:
            wire["params"] = self.params
        if self.trace is not None:
            wire["trace"] = self.trace
        return wire


@dataclass(frozen=True, slots=True)
class SuccessResponse:
    id: RequestId
    result: JsonValue

    def __post_init__(self) -> None:
        _validate_request_id(self.id)
        _validate_json(self.result, "result")

    def to_wire(self) -> dict[str, JsonValue]:
        return {"id": self.id, "result": self.result}


@dataclass(frozen=True, slots=True)
class ErrorResponse:
    id: RequestId
    error: ProtocolError

    def __post_init__(self) -> None:
        _validate_request_id(self.id)
        if not isinstance(self.error, ProtocolError):
            raise ProtocolModelError(
                f"error: expected ProtocolError; got {_category(self.error)}"
            )

    def to_wire(self) -> dict[str, JsonValue]:
        return {"id": self.id, "error": self.error.to_wire()}


@dataclass(frozen=True, slots=True)
class Notification:
    method: str
    params: JsonValue | None = None

    def __post_init__(self) -> None:
        _validate_string(self.method, "method")
        if self.params is not None:
            _validate_json(self.params, "params")

    def to_wire(self) -> dict[str, JsonValue]:
        wire: dict[str, JsonValue] = {"method": self.method}
        if self.params is not None:
            wire["params"] = self.params
        return wire


Envelope: TypeAlias = Request | SuccessResponse | ErrorResponse | Notification


def _construct(model: type[Envelope], /, **members: object) -> Envelope:
    try:
        return model(**members)  # type: ignore[arg-type,call-arg]
    except ProtocolModelError as error:
        raise ProtocolDecodeError(str(error)) from error


def _parse_error(value: object) -> ProtocolError:
    if not isinstance(value, dict):
        raise ProtocolDecodeError(f"error: expected object; got {_category(value)}")
    missing = {"code", "message"} - value.keys()
    if missing:
        raise ProtocolDecodeError(f"error: missing required member {sorted(missing)[0]}")
    return _construct(
        ProtocolError,
        code=value["code"],
        message=value["message"],
        data=value.get("data"),
    )  # type: ignore[return-value]


def parse_envelope(value: JsonValue) -> Envelope:
    """Decode one already-parsed JSON-compatible value into an envelope."""

    if not isinstance(value, dict):
        raise ProtocolDecodeError(f"envelope: expected object; got {_category(value)}")
    if "jsonrpc" in value:
        raise ProtocolDecodeError("jsonrpc: member is not part of the pinned protocol")

    has_id = "id" in value
    has_method = "method" in value
    has_result = "result" in value
    has_error = "error" in value

    if has_result and has_error:
        raise ProtocolDecodeError("envelope: result and error are mutually exclusive")
    if has_method and (has_result or has_error):
        raise ProtocolDecodeError("envelope: method contradicts response members")

    if has_id and has_method:
        return _construct(
            Request,
            id=value["id"],
            method=value["method"],
            params=value.get("params"),
            trace=value.get("trace"),
        )
    if has_method and not has_id:
        return _construct(Notification, method=value["method"], params=value.get("params"))
    if has_id and has_result:
        return _construct(SuccessResponse, id=value["id"], result=value["result"])
    if has_id and has_error:
        error = _parse_error(value["error"])
        return _construct(ErrorResponse, id=value["id"], error=error)
    raise ProtocolDecodeError("envelope: value does not match a supported envelope")
