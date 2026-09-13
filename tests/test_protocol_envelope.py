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
    parse_envelope,
)


class RequestTests(unittest.TestCase):
    def test_exact_shapes_and_optional_members(self) -> None:
        cases = [
            (Request(1, "initialize"), {"id": 1, "method": "initialize"}),
            (Request("1", "x", params={"a": True}),
             {"id": "1", "method": "x", "params": {"a": True}}),
            (Request(2, "x", trace={"traceparent": "value"}),
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
                self.assertEqual(parse_envelope(wire), model)

    def test_null_params_normalizes_to_absent(self) -> None:
        self.assertEqual(parse_envelope({"method": "ready", "params": None}), Notification("ready"))


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

    def test_jsonrpc_is_intentionally_rejected(self) -> None:
        with self.assertRaisesRegex(ProtocolDecodeError, "not part of the pinned protocol"):
            parse_envelope({"jsonrpc": "2.0", "id": 1, "method": "x"})

    def test_non_json_values_are_rejected(self) -> None:
        for result in ((1, 2), math.inf, {1: "value"}):
            with self.subTest(result=result):
                with self.assertRaises(ProtocolModelError):
                    SuccessResponse(1, result)


if __name__ == "__main__":
    unittest.main()
