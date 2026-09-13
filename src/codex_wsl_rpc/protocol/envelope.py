"""Pure value models for the pinned app-server wire envelopes.

The pinned Rust structs use serde's default unknown-member behavior, so extra
members, including ``jsonrpc``, are ignored while decoding.  The pinned protocol
does not emit or require ``jsonrpc`` on the wire.
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
_U64_MAX = 2**64 - 1


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


def _snapshot_json(value: object, path: str) -> JsonValue:
    """Validate and recursively copy one value in the supported JSON domain.

    Normal ``serde_json::Number`` stores integers directly as ``i64`` or
    ``u64`` and otherwise uses a finite ``f64``.  LOCAL MOCK POLICY: Python
    integers must fit the direct integer storage range; this codec rejects
    larger integers instead of silently changing their value or type to float.
    """

    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, int):
        if not _I64_MIN <= value <= _U64_MAX:
            raise ProtocolModelError(f"{path}: JSON integer is out of range")
        return value
    if isinstance(value, float):
        if math.isfinite(value):
            return value
        raise ProtocolModelError(f"{path}: expected a finite JSON number")
    if isinstance(value, list):
        return [
            _snapshot_json(item, f"{path}[{index}]")
            for index, item in enumerate(value)
        ]
    if isinstance(value, dict):
        snapshot: dict[str, JsonValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ProtocolModelError(f"{path}: expected object keys to be strings")
            snapshot[key] = _snapshot_json(item, f"{path}.{key}")
        return snapshot
    raise ProtocolModelError(f"{path}: expected a JSON-compatible value; got {_category(value)}")


@dataclass(frozen=True, slots=True)
class W3cTraceContext:
    """The W3C trace fields accepted by the pinned protocol."""

    traceparent: str
    tracestate: str | None = None

    def __post_init__(self) -> None:
        _validate_string(self.traceparent, "trace.traceparent")
        if self.tracestate is not None:
            _validate_string(self.tracestate, "trace.tracestate")

    def to_wire(self) -> dict[str, JsonValue]:
        wire: dict[str, JsonValue] = {"traceparent": self.traceparent}
        if self.tracestate is not None:
            wire["tracestate"] = self.tracestate
        return wire


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
            object.__setattr__(self, "data", _snapshot_json(self.data, "error.data"))

    def to_wire(self) -> dict[str, JsonValue]:
        wire: dict[str, JsonValue] = {"code": self.code, "message": self.message}
        if self.data is not None:
            wire["data"] = _snapshot_json(self.data, "error.data")
        return wire


@dataclass(frozen=True, slots=True)
class Request:
    id: RequestId
    method: str
    params: JsonValue | None = None
    trace: W3cTraceContext | None = None

    def __post_init__(self) -> None:
        _validate_request_id(self.id)
        _validate_string(self.method, "method")
        if self.params is not None:
            object.__setattr__(self, "params", _snapshot_json(self.params, "params"))
        if self.trace is not None and not isinstance(self.trace, W3cTraceContext):
            raise ProtocolModelError(
                f"trace: expected W3cTraceContext; got {_category(self.trace)}"
            )

    def to_wire(self) -> dict[str, JsonValue]:
        wire: dict[str, JsonValue] = {"id": self.id, "method": self.method}
        if self.params is not None:
            wire["params"] = _snapshot_json(self.params, "params")
        if self.trace is not None:
            wire["trace"] = self.trace.to_wire()
        return wire


@dataclass(frozen=True, slots=True)
class SuccessResponse:
    id: RequestId
    result: JsonValue

    def __post_init__(self) -> None:
        _validate_request_id(self.id)
        object.__setattr__(self, "result", _snapshot_json(self.result, "result"))

    def to_wire(self) -> dict[str, JsonValue]:
        return {"id": self.id, "result": _snapshot_json(self.result, "result")}


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
            object.__setattr__(self, "params", _snapshot_json(self.params, "params"))

    def to_wire(self) -> dict[str, JsonValue]:
        wire: dict[str, JsonValue] = {"method": self.method}
        if self.params is not None:
            wire["params"] = _snapshot_json(self.params, "params")
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


def _parse_trace(value: object) -> W3cTraceContext | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ProtocolDecodeError(f"trace: expected object; got {_category(value)}")
    if "traceparent" not in value:
        raise ProtocolDecodeError("trace: missing required member traceparent")
    try:
        return W3cTraceContext(
            traceparent=value["traceparent"],
            tracestate=value.get("tracestate"),
        )
    except ProtocolModelError as error:
        raise ProtocolDecodeError(str(error)) from error


def parse_envelope(value: JsonValue) -> Envelope:
    """Decode one already-parsed JSON-compatible value into an envelope."""

    if not isinstance(value, dict):
        raise ProtocolDecodeError(f"envelope: expected object; got {_category(value)}")
    has_id = "id" in value
    has_method = "method" in value
    has_result = "result" in value
    has_error = "error" in value

    if has_id and has_method:
        return _construct(
            Request,
            id=value["id"],
            method=value["method"],
            params=value.get("params"),
            trace=_parse_trace(value.get("trace")),
        )
    if has_method and not has_id:
        return _construct(Notification, method=value["method"], params=value.get("params"))
    if has_result and has_error:
        raise ProtocolDecodeError("envelope: result and error are mutually exclusive")
    if has_id and has_result:
        return _construct(SuccessResponse, id=value["id"], result=value["result"])
    if has_id and has_error:
        error = _parse_error(value["error"])
        return _construct(ErrorResponse, id=value["id"], error=error)
    raise ProtocolDecodeError("envelope: value does not match a supported envelope")
