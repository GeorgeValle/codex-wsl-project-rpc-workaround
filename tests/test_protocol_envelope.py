"""Focused tests for the pinned app-server envelope codec."""

from __future__ import annotations

import math
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from codex_wsl_rpc.protocol import (  # noqa: E402
    ErrorResponse,
    Notification,
    ProtocolDecodeError,
    ProtocolError,
    ProtocolModelError,
    Request,
    SuccessResponse,
    W3cTraceContext,
    parse_envelope,
)


class RequestTests(unittest.TestCase):
    def test_exact_shapes_and_optional_members(self) -> None:
        cases = [
            (Request(1, "initialize"), {"id": 1, "method": "initialize"}),
            (Request("1", "x", params={"a": True}),
             {"id": "1", "method": "x", "params": {"a": True}}),
            (Request(2, "x", trace=W3cTraceContext(traceparent="value")),
             {"id": 2, "method": "x", "trace": {"traceparent": "value"}}),
        ]
        for model, wire in cases:
            with self.subTest(wire=wire):
                self.assertEqual(model.to_wire(), wire)
                self.assertNotIn("jsonrpc", model.to_wire())
                self.assertEqual(parse_envelope(wire), model)

    def test_optional_null_normalizes_to_absent_like_pinned_serde_option(self) -> None:
        model = parse_envelope(
            {"id": 1, "method": "x", "params": None, "trace": None}
        )
        self.assertEqual(model, Request(1, "x"))
        self.assertEqual(model.to_wire(), {"id": 1, "method": "x"})

    def test_trace_context_shapes_round_trip(self) -> None:
        contexts = [
            W3cTraceContext(traceparent="parent"),
            W3cTraceContext(traceparent="parent", tracestate="state"),
        ]
        for context in contexts:
            with self.subTest(context=context):
                request = Request(1, "x", trace=context)
                self.assertEqual(parse_envelope(request.to_wire()), request)

    def test_trace_serialization_omits_none_members(self) -> None:
        self.assertEqual(
            W3cTraceContext(traceparent="parent").to_wire(),
            {"traceparent": "parent"},
        )
        self.assertEqual(
            W3cTraceContext(traceparent="parent", tracestate="state").to_wire(),
            {"traceparent": "parent", "tracestate": "state"},
        )

    def test_traceparent_is_required_for_local_construction(self) -> None:
        with self.assertRaises(TypeError):
            W3cTraceContext()
        for traceparent in (None, 123):
            with self.subTest(traceparent=traceparent):
                with self.assertRaises(ProtocolModelError):
                    W3cTraceContext(traceparent=traceparent)

    def test_invalid_local_trace_values_raise_model_error(self) -> None:
        for trace in (1, [], {"traceparent": 1}):
            with self.subTest(trace=trace):
                with self.assertRaises(ProtocolModelError):
                    Request(1, "x", trace=trace)

    def test_invalid_wire_trace_values_raise_decode_error(self) -> None:
        traces = [
            1,
            [],
            {},
            {"tracestate": "state"},
            {"traceparent": None},
            {"traceparent": 123},
            {"traceparent": "parent", "tracestate": []},
        ]
        for trace in traces:
            with self.subTest(trace=trace):
                with self.assertRaises(ProtocolDecodeError):
                    parse_envelope({"id": 1, "method": "x", "trace": trace})

    def test_trace_unknown_members_follow_pinned_serde_policy(self) -> None:
        self.assertEqual(
            parse_envelope(
                {
                    "id": 1,
                    "method": "x",
                    "trace": {"traceparent": "parent", "future": 1},
                }
            ),
            Request(1, "x", trace=W3cTraceContext(traceparent="parent")),
        )

    def test_params_are_snapshotted_at_construction_and_serialization(self) -> None:
        params = {"items": [{"value": 1}]}
        model = Request(1, "x", params=params)
        params["items"][0]["value"] = 2
        wire = model.to_wire()
        wire["params"]["items"][0]["value"] = 3
        self.assertEqual(model.to_wire()["params"], {"items": [{"value": 1}]})


class SuccessResponseTests(unittest.TestCase):
    def test_result_values_and_id_types_round_trip(self) -> None:
        cases = [
            SuccessResponse(1, None),
            SuccessResponse("1", "ok"),
            SuccessResponse(2, {"items": []}),
        ]
        for model in cases:
            with self.subTest(model=model):
                self.assertEqual(parse_envelope(model.to_wire()), model)
                self.assertIn("result", model.to_wire())
                self.assertNotIn("jsonrpc", model.to_wire())

    def test_result_is_snapshotted_at_construction_and_serialization(self) -> None:
        result = {"items": [[1]]}
        model = SuccessResponse(1, result)
        result["items"][0].append(2)
        wire = model.to_wire()
        wire["result"]["items"][0].append(3)
        self.assertEqual(model.to_wire()["result"], {"items": [[1]]})


class ErrorResponseTests(unittest.TestCase):
    def test_exact_shapes_and_round_trip(self) -> None:
        cases = [
            (ErrorResponse(1, ProtocolError(-32600, "bad")),
             {"id": 1, "error": {"code": -32600, "message": "bad"}}),
            (ErrorResponse("1", ProtocolError(-1, "bad", {"why": "x"})),
             {"id": "1", "error": {"code": -1, "message": "bad", "data": {"why": "x"}}}),
        ]
        for model, wire in cases:
            with self.subTest(wire=wire):
                self.assertEqual(model.to_wire(), wire)
                self.assertNotIn("jsonrpc", model.to_wire())
                self.assertEqual(parse_envelope(wire), model)

    def test_null_error_data_normalizes_to_absent(self) -> None:
        model = parse_envelope(
            {"id": 1, "error": {"code": -1, "message": "bad", "data": None}}
        )
        self.assertEqual(model.to_wire(), {"id": 1, "error": {"code": -1, "message": "bad"}})

    def test_malformed_errors_are_decode_errors(self) -> None:
        values = [None, {}, {"code": -1}, {"code": True, "message": "bad"}]
        for error in values:
            with self.subTest(error=error):
                with self.assertRaises(ProtocolDecodeError):
                    parse_envelope({"id": 1, "error": error})

    def test_protocol_error_code_is_signed_64_bit(self) -> None:
        for code in (-(2**63), 2**63 - 1):
            with self.subTest(code=code):
                self.assertEqual(ProtocolError(code, "x").code, code)
        for code in (-(2**63) - 1, 2**63, True):
            with self.subTest(code=code):
                with self.assertRaises(ProtocolModelError):
                    ProtocolError(code, "x")

    def test_error_data_is_snapshotted_through_response_serialization(self) -> None:
        data = {"details": [{"reason": "original"}]}
        model = ErrorResponse(1, ProtocolError(-1, "bad", data))
        data["details"][0]["reason"] = "input mutation"
        wire = model.to_wire()
        wire["error"]["data"]["details"][0]["reason"] = "wire mutation"
        self.assertEqual(
            model.to_wire()["error"]["data"],
            {"details": [{"reason": "original"}]},
        )


class NotificationTests(unittest.TestCase):
    def test_exact_shapes(self) -> None:
        cases = [
            (Notification("ready"), {"method": "ready"}),
            (Notification("ready", {"value": 1}),
             {"method": "ready", "params": {"value": 1}}),
        ]
        for model, wire in cases:
            with self.subTest(wire=wire):
                self.assertEqual(model.to_wire(), wire)
                self.assertNotIn("id", model.to_wire())
                self.assertNotIn("jsonrpc", model.to_wire())
                self.assertEqual(parse_envelope(wire), model)

    def test_null_params_normalizes_to_absent(self) -> None:
        self.assertEqual(parse_envelope({"method": "ready", "params": None}), Notification("ready"))

    def test_params_are_snapshotted_at_construction_and_serialization(self) -> None:
        params = {"items": [{"value": 1}]}
        model = Notification("ready", params)
        params["items"][0]["value"] = 2
        wire = model.to_wire()
        wire["params"]["items"][0]["value"] = 3
        self.assertEqual(model.to_wire()["params"], {"items": [{"value": 1}]})


class RequestIdTests(unittest.TestCase):
    def test_boundaries_and_types_are_preserved(self) -> None:
        for request_id in (-(2**63), 2**63 - 1, "1", 1):
            with self.subTest(request_id=request_id):
                decoded = parse_envelope(Request(request_id, "x").to_wire())
                self.assertEqual(decoded.id, request_id)
                self.assertIs(type(decoded.id), type(request_id))

    def test_invalid_local_ids_raise_model_error(self) -> None:
        values = [-(2**63) - 1, 2**63, True, None, 1.0, [], {}, (), object()]
        for request_id in values:
            with self.subTest(value_type=type(request_id).__name__):
                with self.assertRaises(ProtocolModelError):
                    Request(request_id, "x")

    def test_invalid_wire_ids_raise_decode_error(self) -> None:
        for request_id in (True, None, 1.0, []):
            with self.subTest(request_id=request_id):
                with self.assertRaises(ProtocolDecodeError):
                    parse_envelope({"id": request_id, "method": "x"})


class ClassificationAndPolicyTests(unittest.TestCase):
    def test_four_envelopes_are_classified(self) -> None:
        cases = [
            ({"id": 1, "method": "x"}, Request),
            ({"method": "x"}, Notification),
            ({"id": 1, "result": None}, SuccessResponse),
            ({"id": 1, "error": {"code": -1, "message": "x"}}, ErrorResponse),
        ]
        for wire, expected in cases:
            with self.subTest(wire=wire):
                self.assertIsInstance(parse_envelope(wire), expected)

    def test_ambiguous_unmatched_and_non_object_values_are_rejected(self) -> None:
        values = [
            {"id": 1, "result": None, "error": {"code": -1, "message": "x"}},
            {"id": 1, "method": "x", "result": None},
            {"method": "x", "error": {"code": -1, "message": "x"}},
            {"id": 1},
            [],
        ]
        for value in values:
            with self.subTest(value=value):
                with self.assertRaises(ProtocolDecodeError):
                    parse_envelope(value)

    def test_pinned_serde_policy_ignores_unknown_members(self) -> None:
        self.assertEqual(
            parse_envelope({"id": 1, "method": "x", "future": 2}),
            Request(1, "x"),
        )
        self.assertEqual(
            parse_envelope({"id": 1, "error": {"code": -1, "message": "x", "future": 2}}),
            ErrorResponse(1, ProtocolError(-1, "x")),
        )

    def test_jsonrpc_is_ignored_like_other_unknown_members(self) -> None:
        request = parse_envelope(
            {"jsonrpc": "2.0", "id": 1, "method": "x", "future": "value"}
        )
        self.assertEqual(request, Request(1, "x"))
        self.assertNotIn("jsonrpc", request.to_wire())

        cases = [
            ({"jsonrpc": "2.0", "id": 1, "result": "ok"}, SuccessResponse(1, "ok")),
            ({"jsonrpc": "2.0", "method": "ready"}, Notification("ready")),
        ]
        for wire, expected in cases:
            with self.subTest(wire=wire):
                model = parse_envelope(wire)
                self.assertEqual(model, expected)
                self.assertNotIn("jsonrpc", model.to_wire())

    def test_non_json_values_are_rejected(self) -> None:
        for result in ((1, 2), math.inf, {1: "value"}, {"nested": object()}):
            with self.subTest(result=result):
                with self.assertRaises(ProtocolModelError):
                    SuccessResponse(1, result)

    def test_decoded_payload_is_snapshotted(self) -> None:
        source = {"id": 1, "result": {"items": [1]}}
        model = parse_envelope(source)
        source["result"]["items"].append(2)
        self.assertEqual(model.to_wire()["result"], {"items": [1]})


if __name__ == "__main__":
    unittest.main()
