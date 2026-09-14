"""Shared validation and immutable storage for protocol JSON values."""

from dataclasses import dataclass
import math
from types import MappingProxyType
from typing import Literal, TypeAlias

from .errors import ProtocolModelError

JsonScalar: TypeAlias = None | bool | int | float | str
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]

@dataclass(frozen=True, slots=True)
class _FrozenScalar:
    kind: Literal["null", "bool", "int", "float", "string"]
    value: JsonScalar

FrozenJsonValue: TypeAlias = _FrozenScalar | tuple["FrozenJsonValue", ...] | MappingProxyType[str, "FrozenJsonValue"]
_I64_MIN = -(2**63)
_I64_MAX = 2**63 - 1
_U64_MAX = 2**64 - 1
_U32_MAX = 2**32 - 1

def _category(value: object) -> str:
    return type(value).__name__

def _validate_string(value: object, path: str) -> None:
    if not isinstance(value, str):
        raise ProtocolModelError(f"{path}: expected string; got {_category(value)}")
    if any("\ud800" <= character <= "\udfff" for character in value):
        raise ProtocolModelError(f"{path}: string contains a Unicode surrogate")

def _validate_i64(value: object, path: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ProtocolModelError(f"{path}: expected a signed 64-bit integer; got {_category(value)}")
    if not _I64_MIN <= value <= _I64_MAX:
        raise ProtocolModelError(f"{path}: signed 64-bit integer is out of range")

def _validate_u32(value: object, path: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ProtocolModelError(f"{path}: expected an unsigned 32-bit integer; got {_category(value)}")
    if not 0 <= value <= _U32_MAX:
        raise ProtocolModelError(f"{path}: unsigned 32-bit integer is out of range")

def _freeze_json(value: object, path: str) -> FrozenJsonValue:
    if value is None: return _FrozenScalar("null", value)
    if isinstance(value, bool): return _FrozenScalar("bool", value)
    if isinstance(value, str):
        _validate_string(value, path); return _FrozenScalar("string", value)
    if isinstance(value, int):
        if not _I64_MIN <= value <= _U64_MAX: raise ProtocolModelError(f"{path}: JSON integer is out of range")
        return _FrozenScalar("int", value)
    if isinstance(value, float):
        if not math.isfinite(value): raise ProtocolModelError(f"{path}: expected a finite JSON number")
        return _FrozenScalar("float", value)
    if isinstance(value, list):
        return tuple(_freeze_json(item, f"{path}[{index}]") for index, item in enumerate(value))
    if isinstance(value, dict):
        frozen = {}
        for key, item in value.items():
            if not isinstance(key, str): raise ProtocolModelError(f"{path}: expected object keys to be strings")
            _validate_string(key, f"{path} key")
            frozen[key] = _freeze_json(item, f"{path}.{key}")
        return MappingProxyType(frozen)
    raise ProtocolModelError(f"{path}: expected a JSON-compatible value; got {_category(value)}")

def _thaw_json(value: FrozenJsonValue) -> JsonValue:
    if isinstance(value, _FrozenScalar): return value.value
    if isinstance(value, tuple): return [_thaw_json(item) for item in value]
    if isinstance(value, MappingProxyType): return {key: _thaw_json(item) for key, item in value.items()}
    return value
