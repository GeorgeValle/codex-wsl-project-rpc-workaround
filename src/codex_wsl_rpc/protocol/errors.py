"""Local errors for protocol value construction and decoding."""


class ProtocolModelError(ValueError):
    """An invalid value was supplied to a local protocol model."""


class ProtocolDecodeError(ValueError):
    """A JSON-compatible value does not have a valid protocol shape."""
