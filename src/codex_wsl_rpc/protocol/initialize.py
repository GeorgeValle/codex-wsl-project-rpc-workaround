"""Pure initialization schema models for the pinned protocol."""

from dataclasses import InitVar, dataclass, field
from typing import Self

from ._values import FrozenJsonValue, JsonValue, _category, _freeze_json, _thaw_json, _validate_string
from .errors import ProtocolDecodeError, ProtocolModelError

def _object(value: JsonValue, path: str) -> dict[str, JsonValue]:
    try: _freeze_json(value, path)
    except ProtocolModelError as error: raise ProtocolDecodeError(str(error)) from error
    if not isinstance(value, dict): raise ProtocolDecodeError(f"{path}: expected object; got {_category(value)}")
    return value

def _decode(cls: type[Self], members: dict[str, object]) -> Self:
    try: return cls(**members)
    except (ProtocolModelError, TypeError) as error: raise ProtocolDecodeError(str(error)) from error

@dataclass(frozen=True, slots=True)
class ClientInfo:
    name: str
    version: str
    title: str | None = None
    def __post_init__(self) -> None:
        _validate_string(self.name, "clientInfo.name"); _validate_string(self.version, "clientInfo.version")
        if self.title is not None: _validate_string(self.title, "clientInfo.title")
    @classmethod
    def from_wire(cls, value: JsonValue) -> Self:
        obj = _object(value, "clientInfo")
        for key in ("name", "version"):
            if key not in obj: raise ProtocolDecodeError(f"clientInfo: missing required member {key}")
        return _decode(cls, {"name": obj["name"], "version": obj["version"], "title": obj.get("title")})
    def to_wire(self) -> dict[str, JsonValue]: return {"name": self.name, "title": self.title, "version": self.version}

@dataclass(frozen=True, slots=True)
class InitializeCapabilities:
    experimental_api: bool = False
    request_attestation: bool = False
    mcp_server_openai_form_elicitation: bool = False
    opt_out_notification_methods: tuple[str, ...] | None = None
    extensions: InitVar[dict[str, JsonValue] | None] = None
    _extensions_frozen: FrozenJsonValue | None = field(init=False, repr=False)
    def __post_init__(self, extensions: dict[str, JsonValue] | None) -> None:
        for name, value in (("experimental_api", self.experimental_api), ("request_attestation", self.request_attestation), ("mcp_server_openai_form_elicitation", self.mcp_server_openai_form_elicitation)):
            if not isinstance(value, bool): raise ProtocolModelError(f"{name}: expected bool; got {_category(value)}")
        if self.opt_out_notification_methods is not None:
            if not isinstance(self.opt_out_notification_methods, (tuple, list)): raise ProtocolModelError("opt_out_notification_methods: expected sequence")
            methods = tuple(self.opt_out_notification_methods)
            for item in methods: _validate_string(item, "optOutNotificationMethods item")
            object.__setattr__(self, "opt_out_notification_methods", methods)
        if extensions is not None and not isinstance(extensions, dict): raise ProtocolModelError("extensions: expected object")
        object.__setattr__(self, "_extensions_frozen", None if extensions is None else _freeze_json(extensions, "extensions"))
    def _get_extensions(self) -> dict[str, JsonValue] | None:
        if self._extensions_frozen is None: return None
        value = _thaw_json(self._extensions_frozen); assert isinstance(value, dict); return value
    @classmethod
    def from_wire(cls, value: JsonValue) -> Self:
        obj = _object(value, "capabilities")
        return _decode(cls, {"experimental_api": obj.get("experimentalApi", False), "request_attestation": obj.get("requestAttestation", False), "mcp_server_openai_form_elicitation": obj.get("mcpServerOpenaiFormElicitation", False), "opt_out_notification_methods": obj.get("optOutNotificationMethods"), "extensions": obj.get("extensions")})
    def to_wire(self) -> dict[str, JsonValue]:
        wire: dict[str, JsonValue] = {"experimentalApi": self.experimental_api, "requestAttestation": self.request_attestation, "optOutNotificationMethods": None if self.opt_out_notification_methods is None else list(self.opt_out_notification_methods)}
        if self.mcp_server_openai_form_elicitation: wire["mcpServerOpenaiFormElicitation"] = True
        if self._extensions_frozen is not None: wire["extensions"] = _thaw_json(self._extensions_frozen)
        return wire

InitializeCapabilities.extensions = property(InitializeCapabilities._get_extensions)  # type: ignore[assignment]

@dataclass(frozen=True, slots=True)
class InitializeParams:
    client_info: ClientInfo
    capabilities: InitializeCapabilities | None = None
    def __post_init__(self) -> None:
        if not isinstance(self.client_info, ClientInfo): raise ProtocolModelError("client_info: expected ClientInfo")
        if self.capabilities is not None and not isinstance(self.capabilities, InitializeCapabilities): raise ProtocolModelError("capabilities: expected InitializeCapabilities")
    @classmethod
    def from_wire(cls, value: JsonValue) -> Self:
        obj = _object(value, "initialize")
        if "clientInfo" not in obj: raise ProtocolDecodeError("initialize: missing required member clientInfo")
        info = ClientInfo.from_wire(obj["clientInfo"])
        caps = None if obj.get("capabilities") is None else InitializeCapabilities.from_wire(obj["capabilities"])
        return cls(info, caps)
    def to_wire(self) -> dict[str, JsonValue]:
        wire: dict[str, JsonValue] = {"clientInfo": self.client_info.to_wire()}
        if self.capabilities is not None: wire["capabilities"] = self.capabilities.to_wire()
        return wire

@dataclass(frozen=True, slots=True)
class InitializeResponse:
    user_agent: str; codex_home: str; platform_family: str; platform_os: str
    def __post_init__(self) -> None:
        for name, value in (("userAgent", self.user_agent), ("codexHome", self.codex_home), ("platformFamily", self.platform_family), ("platformOs", self.platform_os)): _validate_string(value, name)
    @classmethod
    def from_wire(cls, value: JsonValue) -> Self:
        obj = _object(value, "initialize response"); keys = ("userAgent", "codexHome", "platformFamily", "platformOs")
        for key in keys:
            if key not in obj: raise ProtocolDecodeError(f"initialize response: missing required member {key}")
        return _decode(cls, dict(zip(("user_agent", "codex_home", "platform_family", "platform_os"), (obj[key] for key in keys))))
    def to_wire(self) -> dict[str, JsonValue]: return {"userAgent": self.user_agent, "codexHome": self.codex_home, "platformFamily": self.platform_family, "platformOs": self.platform_os}
