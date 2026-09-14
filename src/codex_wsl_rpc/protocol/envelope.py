"""Pure value models for the pinned app-server wire envelopes.

The pinned Rust structs use serde's default unknown-member behavior, so extra
members, including ``jsonrpc``, are ignored while decoding.  The pinned protocol
does not emit or require ``jsonrpc`` on the wire.
"""

from __future__ import annotations

from dataclasses import InitVar, dataclass, field
import math
from types import MappingProxyType
from typing import Callable, Literal, TypeAlias

from .errors import ProtocolDecodeError, ProtocolModelError


JsonScalar: TypeAlias = None | bool | int | float | str
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]


@dataclass(frozen=True, slots=True)
class _FrozenScalar:
    """A JSON scalar whose equality preserves its wire type."""

    kind: Literal["null", "bool", "int", "float", "string"]
    value: JsonScalar


FrozenJsonValue: TypeAlias = (
    _FrozenScalar
    | tuple["FrozenJsonValue", ...]
    | MappingProxyType[str, "FrozenJsonValue"]
)
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
        _validate_string(value, path)
        return
    _validate_i64(value, path)


def _validate_string(value: object, path: str) -> None:
    if not isinstance(value, str):
        raise ProtocolModelError(f"{path}: expected string; got {_category(value)}")
    if any("\ud800" <= character <= "\udfff" for character in value):
        raise ProtocolModelError(f"{path}: string contains a Unicode surrogate")


def _freeze_json(value: object, path: str) -> FrozenJsonValue:
    """Validate and recursively freeze one value in the supported JSON domain.

    Normal ``serde_json::Number`` stores integers directly as ``i64`` or
    ``u64`` and otherwise uses a finite ``f64``.  LOCAL MOCK POLICY: Python
    integers must fit the direct integer storage range; this codec rejects
    larger integers instead of silently changing their value or type to float.
    """

    if value is None:
        return _FrozenScalar("null", value)
    if isinstance(value, bool):
        return _FrozenScalar("bool", value)
    if isinstance(value, str):
        _validate_string(value, path)
        return _FrozenScalar("string", value)
    if isinstance(value, int):
        if not _I64_MIN <= value <= _U64_MAX:
            raise ProtocolModelError(f"{path}: JSON integer is out of range")
        return _FrozenScalar("int", value)
    if isinstance(value, float):
        if math.isfinite(value):
            return _FrozenScalar("float", value)
        raise ProtocolModelError(f"{path}: expected a finite JSON number")
    if isinstance(value, list):
        return tuple(
            _freeze_json(item, f"{path}[{index}]")
            for index, item in enumerate(value)
        )
    if isinstance(value, dict):
        frozen: dict[str, FrozenJsonValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ProtocolModelError(f"{path}: expected object keys to be strings")
            _validate_string(key, f"{path} key")
            frozen[key] = _freeze_json(item, f"{path}.{key}")
        return MappingProxyType(frozen)
    raise ProtocolModelError(f"{path}: expected a JSON-compatible value; got {_category(value)}")


def _thaw_json(value: FrozenJsonValue) -> JsonValue:
    """Return a fresh ordinary JSON-compatible representation of a frozen value."""

    if isinstance(value, _FrozenScalar):
        return value.value
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    if isinstance(value, MappingProxyType):
        return {key: _thaw_json(item) for key, item in value.items()}
    return value


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
    data: InitVar[JsonValue | None] = None
    _data_frozen: FrozenJsonValue | None = field(init=False, repr=False)

    def __post_init__(self, data: JsonValue | None) -> None:
        _validate_i64(self.code, "error.code")
        _validate_string(self.message, "error.message")
        object.__setattr__(
            self,
            "_data_frozen",
            None if data is None else _freeze_json(data, "error.data"),
        )

    def _get_data(self) -> JsonValue | None:
        if self._data_frozen is None:
            return None
        return _thaw_json(self._data_frozen)

    def to_wire(self) -> dict[str, JsonValue]:
        wire: dict[str, JsonValue] = {"code": self.code, "message": self.message}
        if self._data_frozen is not None:
            wire["data"] = _thaw_json(self._data_frozen)
        return wire


@dataclass(frozen=True, slots=True)
class Request:
    id: RequestId
    method: str
    params: InitVar[JsonValue | None] = None
    trace: W3cTraceContext | None = None
    _params_frozen: FrozenJsonValue | None = field(init=False, repr=False)

    def __post_init__(self, params: JsonValue | None) -> None:
        _validate_request_id(self.id)
        _validate_string(self.method, "method")
        object.__setattr__(
            self,
            "_params_frozen",
            None if params is None else _freeze_json(params, "params"),
        )
        if self.trace is not None and not isinstance(self.trace, W3cTraceContext):
            raise ProtocolModelError(
                f"trace: expected W3cTraceContext; got {_category(self.trace)}"
            )

    def _get_params(self) -> JsonValue | None:
        if self._params_frozen is None:
            return None
        return _thaw_json(self._params_frozen)

    def to_wire(self) -> dict[str, JsonValue]:
        wire: dict[str, JsonValue] = {"id": self.id, "method": self.method}
        if self._params_frozen is not None:
            wire["params"] = _thaw_json(self._params_frozen)
        if self.trace is not None:
            wire["trace"] = self.trace.to_wire()
        return wire


@dataclass(frozen=True, slots=True)
class SuccessResponse:
    id: RequestId
    result: InitVar[JsonValue]
    _result_frozen: FrozenJsonValue = field(init=False, repr=False)

    def __post_init__(self, result: JsonValue) -> None:
        _validate_request_id(self.id)
        object.__setattr__(self, "_result_frozen", _freeze_json(result, "result"))

    def _get_result(self) -> JsonValue:
        return _thaw_json(self._result_frozen)

    @property
    def result(self) -> JsonValue:
        return self._get_result()

    def to_wire(self) -> dict[str, JsonValue]:
        return {"id": self.id, "result": _thaw_json(self._result_frozen)}


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
    params: InitVar[JsonValue | None] = None
    _params_frozen: FrozenJsonValue | None = field(init=False, repr=False)

    def __post_init__(self, params: JsonValue | None) -> None:
        _validate_string(self.method, "method")
        object.__setattr__(
            self,
            "_params_frozen",
            None if params is None else _freeze_json(params, "params"),
        )

    def _get_params(self) -> JsonValue | None:
        if self._params_frozen is None:
            return None
        return _thaw_json(self._params_frozen)

    def to_wire(self) -> dict[str, JsonValue]:
        wire: dict[str, JsonValue] = {"method": self.method}
        if self._params_frozen is not None:
            wire["params"] = _thaw_json(self._params_frozen)
        return wire


# InitVar keeps the public constructor names available to dataclasses.replace;
# properties then expose fresh JSON-compatible copies rather than frozen storage.
ProtocolError.data = property(ProtocolError._get_data)  # type: ignore[assignment]
Request.params = property(Request._get_params)  # type: ignore[assignment]
Notification.params = property(Notification._get_params)  # type: ignore[assignment]


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


def _try_candidate(factory: Callable[[], Envelope]) -> Envelope | None:
    """Return a constructed candidate, or allow an expected decode failure to fall through."""

    try:
        return factory()
    except ProtocolDecodeError:
        return None


def parse_envelope(value: JsonValue) -> Envelope:
    """Decode one already-parsed JSON-compatible value into an envelope."""

    try:
        _freeze_json(value, "envelope")
    except ProtocolModelError as error:
        raise ProtocolDecodeError(str(error)) from error
    if not isinstance(value, dict):
        raise ProtocolDecodeError(f"envelope: expected object; got {_category(value)}")
    has_id = "id" in value
    has_method = "method" in value
    has_result = "result" in value
    has_error = "error" in value

    candidates: list[Callable[[], Envelope]] = []
    if has_id and has_method:
        candidates.append(
            lambda: _construct(
                Request,
                id=value["id"],
                method=value["method"],
                params=value.get("params"),
                trace=_parse_trace(value.get("trace")),
            )
        )
    if has_method:
        candidates.append(
            lambda: _construct(
                Notification,
                method=value["method"],
                params=value.get("params"),
            )
        )
    if has_id and has_result:
        candidates.append(
            lambda: _construct(SuccessResponse, id=value["id"], result=value["result"])
        )
    if has_id and has_error:
        candidates.append(
            lambda: _construct(
                ErrorResponse,
                id=value["id"],
                error=_parse_error(value["error"]),
            )
        )

    for factory in candidates:
        candidate = _try_candidate(factory)
        if candidate is not None:
            return candidate
    raise ProtocolDecodeError("envelope: value does not match a supported envelope")
