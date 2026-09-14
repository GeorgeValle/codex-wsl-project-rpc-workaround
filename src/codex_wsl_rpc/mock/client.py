"""Small typed client for the in-memory mock transport only."""

from __future__ import annotations

import json

from codex_wsl_rpc.protocol import (
    ClientInfo, ErrorResponse, InitializeCapabilities, InitializeParams,
    InitializeResponse, Notification, ProjectListParams, ProjectListResponse,
    ProtocolError, Request, SuccessResponse, parse_envelope,
)

from .transport import InMemoryTransport


class MockServerError(RuntimeError):
    def __init__(self, error: ProtocolError) -> None:
        super().__init__(error.message)
        self.error = error


class MockClient:
    def __init__(self, transport: InMemoryTransport) -> None:
        if not isinstance(transport, InMemoryTransport):
            raise TypeError("transport must be an InMemoryTransport")
        self._transport = transport
        self._next_id = 1

    def initialize(self, client_info: ClientInfo,
                   capabilities: InitializeCapabilities | None = None) -> InitializeResponse:
        params = InitializeParams(client_info, capabilities)
        return InitializeResponse.from_wire(self._request("initialize", params.to_wire()).result)

    def send_initialized(self) -> None:
        line = json.dumps(Notification("initialized").to_wire()) + "\n"
        if self._transport.send(line) is not None:
            raise RuntimeError("mock notification unexpectedly produced a response")

    def list_projects(self, params: ProjectListParams | None = None) -> ProjectListResponse:
        params = ProjectListParams() if params is None else params
        return ProjectListResponse.from_wire(self._request("project/list", params.to_wire()).result)

    def _request(self, method: str, params: dict[str, object]) -> SuccessResponse:
        request_id = self._next_id
        self._next_id += 1
        line = json.dumps(Request(request_id, method, params).to_wire()) + "\n"
        response_line = self._transport.send(line)
        if response_line is None:
            raise RuntimeError("mock request did not produce a response")
        response = parse_envelope(json.loads(response_line[:-1]))
        if not isinstance(response, (SuccessResponse, ErrorResponse)) or response.id != request_id:
            raise RuntimeError("mock response id mismatch")
        if isinstance(response, ErrorResponse):
            raise MockServerError(response.error)
        return response
