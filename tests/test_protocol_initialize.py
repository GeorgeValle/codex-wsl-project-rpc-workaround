import dataclasses
import math
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from codex_wsl_rpc.protocol import (ClientInfo, InitializeCapabilities,  # noqa: E402
    InitializeParams, InitializeResponse, ProtocolDecodeError, ProtocolModelError)

class InitializationTests(unittest.TestCase):
    def test_client_info_wire_rules(self):
        self.assertEqual(ClientInfo.from_wire({"name":"n","version":"1"}).to_wire(), {"name":"n","title":None,"version":"1"})
        self.assertEqual(ClientInfo.from_wire({"name":"bad header\n","title":"T","version":"1","future":[]}).title, "T")
        for value in ({"version":"1"},{"name":"n"},{"name":None,"version":"1"},{"name":"n","version":None}):
            with self.assertRaises(ProtocolDecodeError): ClientInfo.from_wire(value)
        with self.assertRaises(ProtocolDecodeError): ClientInfo.from_wire({"name":"n","version":"1","future":math.nan})

    def test_capability_defaults_and_encoding(self):
        model = InitializeCapabilities.from_wire({})
        self.assertEqual(model.to_wire(), {"experimentalApi":False,"requestAttestation":False,"optOutNotificationMethods":None})
        model = InitializeCapabilities.from_wire({"experimentalApi":True,"requestAttestation":True,"mcpServerOpenaiFormElicitation":True,"optOutNotificationMethods":["x"],"extensions":{"b":True,"i":1,"f":1.0}})
        self.assertEqual(model.to_wire()["extensions"], {"b":True,"i":1,"f":1.0})
        self.assertIs(type(model.to_wire()["extensions"]["b"]), bool)
        self.assertEqual(dataclasses.replace(model, request_attestation=False).extensions, model.extensions)
        exposed=model.extensions; exposed["i"]=2
        self.assertEqual(model.extensions["i"], 1)

    def test_capability_invalid_values(self):
        for key in ("experimentalApi","requestAttestation","mcpServerOpenaiFormElicitation"):
            for value in (0,"false",None):
                with self.assertRaises(ProtocolDecodeError): InitializeCapabilities.from_wire({key:value})
        for wire in ({"optOutNotificationMethods":[1]}, {"extensions":{1:"x"}}, {"extensions":{"x":math.inf}}):
            with self.assertRaises(ProtocolDecodeError): InitializeCapabilities.from_wire(wire)

    def test_params_missing_null_and_empty_capabilities(self):
        base={"clientInfo":{"name":"n","version":"1"}}
        self.assertIsNone(InitializeParams.from_wire(base).capabilities)
        self.assertNotIn("capabilities", InitializeParams.from_wire({**base,"capabilities":None}).to_wire())
        self.assertFalse(InitializeParams.from_wire({**base,"capabilities":{}}).capabilities.experimental_api)
        for wire in ({}, {"clientInfo":None}):
            with self.assertRaises(ProtocolDecodeError): InitializeParams.from_wire(wire)

    def test_response_is_data_only(self):
        wire={"userAgent":"ua","codexHome":"/model/value","platformFamily":"unix","platformOs":"linux"}
        self.assertEqual(InitializeResponse.from_wire(wire).to_wire(), wire)
        with self.assertRaises(ProtocolDecodeError): InitializeResponse.from_wire({"userAgent":"ua"})
        with self.assertRaises(ProtocolModelError): InitializeResponse("ua", None, "x", "y")

if __name__ == "__main__": unittest.main()
