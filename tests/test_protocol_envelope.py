"""Focused tests for the pinned app-server envelope codec."""

from __future__ import annotations

import dataclasses
import json
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

    def test_invalid_request_trace_values_fall_through_to_notification(self) -> None:
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
                self.assertEqual(
                    parse_envelope({"id": 1, "method": "x", "trace": trace}),
                    Notification("x"),
                )

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

    def test_public_params_are_json_compatible_and_isolated(self) -> None:
        model = Request(1, "x", params={"items": [{"value": 1}]})
        exposed = model.params
        self.assertEqual(json.loads(json.dumps(exposed)), exposed)
        exposed["items"].append({"value": 2})
        exposed["items"][0]["value"] = 3
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

    def test_public_result_is_json_compatible_and_isolated(self) -> None:
        model = SuccessResponse(1, {"items": [{"value": 1}]})
        exposed = model.result
        self.assertEqual(json.loads(json.dumps(exposed)), exposed)
        exposed["items"].append({"value": 2})
        exposed["items"][0]["value"] = 3
        self.assertEqual(model.to_wire()["result"], {"items": [{"value": 1}]})

    def test_dataclasses_replace_preserves_public_payload(self) -> None:
        model = SuccessResponse(1, {"items": [1]})
        replaced = dataclasses.replace(model, id=2)
        self.assertEqual(replaced, SuccessResponse(2, {"items": [1]}))

    def test_json_scalar_equality_preserves_wire_types_recursively(self) -> None:
        unequal_pairs = [
            (True, 1),
            (False, 0),
            (1, 1.0),
            ({"value": True}, {"value": 1}),
            ([True], [1]),
        ]
        for left, right in unequal_pairs:
            with self.subTest(left=left, right=right):
                self.assertNotEqual(SuccessResponse(1, left), SuccessResponse(1, right))
        self.assertEqual(SuccessResponse(1, {"value": 1}), SuccessResponse(1, {"value": 1}))
        self.assertNotEqual(Request(1, "x", True), Request(1, "x", 1))
        self.assertNotEqual(Notification("x", [True]), Notification("x", [1]))
        self.assertNotEqual(ProtocolError(-1, "x", True), ProtocolError(-1, "x", 1))

    def test_json_scalar_types_survive_wire_round_trip(self) -> None:
        for result in (True, 1, 1.0, {"value": True}, [1.0]):
            with self.subTest(result=result):
                wire_result = SuccessResponse(1, result).to_wire()["result"]
                self.assertEqual(wire_result, result)
                if not isinstance(result, (dict, list)):
                    self.assertIs(type(wire_result), type(result))


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

    def test_public_error_data_is_json_compatible_and_isolated(self) -> None:
        model = ErrorResponse(
            1, ProtocolError(-1, "bad", {"items": [{"value": 1}]})
        )
        exposed = model.error.data
        self.assertEqual(json.loads(json.dumps(exposed)), exposed)
        exposed["items"].append({"value": 2})
        exposed["items"][0]["value"] = 3
        self.assertEqual(
            model.to_wire()["error"]["data"], {"items": [{"value": 1}]}
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

    def test_public_params_are_json_compatible_and_isolated(self) -> None:
        model = Notification("ready", {"items": [{"value": 1}]})
        exposed = model.params
        self.assertEqual(json.loads(json.dumps(exposed)), exposed)
        exposed["items"].append({"value": 2})
        exposed["items"][0]["value"] = 3
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
                    parse_envelope({"id": request_id, "result": "ok"})


class GenericJsonNumberTests(unittest.TestCase):
    def test_small_integer_and_direct_integer_boundaries_are_accepted(self) -> None:
        for result in (1, -(2**63), 2**64 - 1):
            with self.subTest(result=result):
                model = SuccessResponse(1, result)
                self.assertEqual(model.to_wire()["result"], result)

    def test_values_immediately_outside_direct_integer_boundaries_are_rejected(self) -> None:
        for result in (-(2**63) - 1, 2**64):
            with self.subTest(result=result):
                with self.assertRaises(ProtocolModelError):
                    SuccessResponse(1, result)

    def test_oversized_integer_is_rejected_at_construction(self) -> None:
        with self.assertRaises(ProtocolModelError):
            SuccessResponse(1, 10**400)

    def test_nested_oversized_integer_is_rejected_at_construction(self) -> None:
        with self.assertRaises(ProtocolModelError):
            SuccessResponse(1, {"items": [10**400]})

    def test_oversized_integer_is_rejected_during_decode(self) -> None:
        for result in (10**400, {"items": [10**400]}):
            with self.subTest(result=result):
                with self.assertRaises(ProtocolDecodeError):
                    parse_envelope({"id": 1, "result": result})


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

    def test_unmatched_and_non_object_values_are_rejected(self) -> None:
        values = [
            {"id": 1},
            [],
        ]
        for value in values:
            with self.subTest(value=value):
                with self.assertRaises(ProtocolDecodeError):
                    parse_envelope(value)

    def test_success_response_wins_when_result_and_error_are_present(self) -> None:
        model = parse_envelope(
            {
                "id": 1,
                "result": {"ok": True},
                "error": {"code": -1, "message": "ignored"},
            }
        )
        self.assertIsInstance(model, SuccessResponse)
        self.assertEqual(model.to_wire(), {"id": 1, "result": {"ok": True}})

    def test_invalid_request_falls_through_to_success_response(self) -> None:
        model = parse_envelope({"id": 1, "method": 2, "result": "ok"})
        self.assertEqual(model, SuccessResponse(1, "ok"))

    def test_invalid_request_falls_through_to_error_response(self) -> None:
        model = parse_envelope(
            {
                "id": 1,
                "method": 2,
                "error": {"code": -1, "message": "failed"},
            }
        )
        self.assertEqual(model, ErrorResponse(1, ProtocolError(-1, "failed")))

    def test_valid_request_wins_over_later_candidate(self) -> None:
        model = parse_envelope({"id": 1, "method": "x", "result": "ignored"})
        self.assertEqual(model, Request(1, "x"))

    def test_valid_notification_wins_over_later_candidate(self) -> None:
        model = parse_envelope({"method": "x", "id": [], "result": "ignored"})
        self.assertEqual(model, Notification("x"))

    def test_all_present_candidates_can_fail(self) -> None:
        with self.assertRaises(ProtocolDecodeError):
            parse_envelope(
                {
                    "id": [],
                    "method": 2,
                    "result": object(),
                    "error": {"code": "bad", "message": 3},
                }
            )

    def test_error_response_is_selected_without_result(self) -> None:
        model = parse_envelope(
            {"id": 1, "error": {"code": -1, "message": "failed"}}
        )
        self.assertIsInstance(model, ErrorResponse)

    def test_requests_ignore_response_named_extra_members(self) -> None:
        cases = [
            {"id": 1, "method": "x", "result": {"ignored": True}},
            {"id": 1, "method": "x", "error": {"code": -1, "message": "ignored"}},
            {
                "id": 1,
                "method": "x",
                "result": 1,
                "error": {"code": -1, "message": "ignored"},
            },
        ]
        for wire in cases:
            with self.subTest(wire=wire):
                model = parse_envelope(wire)
                self.assertEqual(model, Request(1, "x"))
                self.assertNotIn("result", model.to_wire())
                self.assertNotIn("error", model.to_wire())

    def test_notifications_ignore_response_named_extra_members(self) -> None:
        model = parse_envelope(
            {"method": "ready", "result": 1, "error": {"ignored": True}}
        )
        self.assertEqual(model, Notification("ready"))
        self.assertEqual(model.to_wire(), {"method": "ready"})

    def test_pinned_serde_policy_ignores_unknown_members(self) -> None:
        self.assertEqual(
            parse_envelope({"id": 1, "method": "x", "future": 2}),
            Request(1, "x"),
        )
        self.assertEqual(
            parse_envelope({"id": 1, "error": {"code": -1, "message": "x", "future": 2}}),
            ErrorResponse(1, ProtocolError(-1, "x")),
        )

    def test_complete_input_tree_is_validated_before_classification(self) -> None:
        invalid_unknown_values = [
            math.nan,
            {"nested": math.inf},
            {"value": 10**400},
        ]
        for future in invalid_unknown_values:
            with self.subTest(future=future):
                with self.assertRaises(ProtocolDecodeError):
                    parse_envelope({"id": 1, "result": "ok", "future": future})

    def test_valid_unknown_json_value_is_still_ignored(self) -> None:
        model = parse_envelope(
            {"id": 1, "result": "ok", "future": {"valid": [1, 2, 3]}}
        )
        self.assertEqual(model, SuccessResponse(1, "ok"))

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


class UnicodeStringTests(unittest.TestCase):
    def test_surrogates_are_rejected_in_json_values_and_keys(self) -> None:
        values = ["\ud800", "\udfff", "ok\ud800bad", {"items": [{"name": "\ud800"}]}, {"\udfff": "value"}]
        for result in values:
            with self.subTest(result=repr(result)):
                with self.assertRaises(ProtocolModelError):
                    SuccessResponse(1, result)

    def test_surrogates_are_rejected_in_protocol_string_fields(self) -> None:
        constructors = [
            lambda: Request("\ud800", "x"),
            lambda: Request(1, "x\udfff"),
            lambda: ProtocolError(-1, "bad\ud800"),
            lambda: W3cTraceContext("parent\ud800"),
            lambda: W3cTraceContext("parent", "state\udfff"),
        ]
        for constructor in constructors:
            with self.subTest(constructor=constructor):
                with self.assertRaises(ProtocolModelError):
                    constructor()

    def test_decode_errors_remain_separate_from_model_errors(self) -> None:
        for wire in ({"id": 1, "result": "\ud800"}, {"id": 1, "result": {"\udfff": 1}}):
            with self.subTest(wire=repr(wire)):
                with self.assertRaises(ProtocolDecodeError):
                    parse_envelope(wire)

    def test_valid_unicode_strings_are_accepted(self) -> None:
        for value in ("á", "漢字", "🙂", "𝄞"):
            with self.subTest(value=value):
                model = SuccessResponse(1, {value: value})
                self.assertEqual(model.to_wire()["result"], {value: value})


if __name__ == "__main__":
    unittest.main()
