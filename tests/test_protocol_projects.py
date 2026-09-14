import math
import unittest

from codex_wsl_rpc.protocol import (Project, ProjectListParams, ProjectListResponse,
    ProjectRoot, ProjectSortKey, ProtocolDecodeError, ProtocolModelError, Request,
    SortDirection, SuccessResponse)

def project_wire():
    return {"id":"p","name":"","roots":[{"path":"/work"}],"metadata":{"b":"2","a":"1"},"position":0,"createdAt":-(2**63),"updatedAt":2**63-1,"recencyAt":None}

class ProjectTests(unittest.TestCase):
    def test_root_local_policy_and_spelling(self):
        for path in ("/x/../y", "C:\\x", "D:/x", "\\\\server\\share\\x"):
            self.assertEqual(ProjectRoot(path).to_wire()["path"], path)
        for path in ("foo/bar","./foo","../foo","~ /x","\ud800"):
            with self.assertRaises(ProtocolModelError): ProjectRoot(path)

    def test_project_shape_boundaries_and_ownership(self):
        source=project_wire(); model=Project.from_wire(source)
        source["roots"][0]["path"]="/changed"; source["metadata"]["a"]="changed"
        self.assertEqual(model.to_wire(), project_wire())
        wire=model.to_wire(); wire["metadata"]["a"]="changed"; self.assertEqual(model.metadata["a"],"1")
        self.assertEqual(model, Project.from_wire({**project_wire(),"metadata":{"a":"1","b":"2"}}))
        self.assertEqual(SuccessResponse(1, model.to_wire()).result, model.to_wire())
        self.assertEqual(Request(1,"project/list",ProjectListParams().to_wire()).params["limit"], None)

    def test_project_invalid_fields(self):
        cases=[{}, {**project_wire(),"roots":None}, {**project_wire(),"roots":[{"path":"relative"}]}, {**project_wire(),"metadata":{"x":1}}, {**project_wire(),"position":True}, {**project_wire(),"createdAt":-(2**63)-1}, {**project_wire(),"updatedAt":2**63}]
        for wire in cases:
            with self.assertRaises(ProtocolDecodeError): Project.from_wire(wire)
        self.assertEqual(Project.from_wire({**project_wire(),"roots":[],"recencyAt":1}).recency_at,1)
        with self.assertRaises(ProtocolDecodeError): Project.from_wire({**project_wire(),"future":math.nan})

    def test_enums_and_list_params_schema_only(self):
        self.assertEqual(ProjectSortKey("position"), ProjectSortKey.POSITION)
        self.assertEqual(SortDirection("desc"), SortDirection.DESC)
        for enum,value in ((ProjectSortKey,"POSITION"),(SortDirection,"ASC")):
            with self.assertRaises(ValueError): enum(value)
        self.assertEqual(ProjectListParams().to_wire(), {"cursor":None,"limit":None,"sortKey":None,"sortDirection":None})
        for limit in (0,101,2**32-1): self.assertEqual(ProjectListParams.from_wire({"limit":limit}).limit,limit)
        for limit in (-1,2**32,1.0,True):
            with self.assertRaises(ProtocolDecodeError): ProjectListParams.from_wire({"limit":limit})
        model=ProjectListParams.from_wire({"cursor":"opaque🙂","sortDirection":"asc"})
        self.assertIsNone(model.sort_key); self.assertEqual(model.sort_direction,SortDirection.ASC)

    def test_list_response(self):
        model=ProjectListResponse.from_wire({"data":[project_wire()]})
        self.assertEqual(model.to_wire()["nextCursor"],None)
        self.assertEqual(ProjectListResponse.from_wire({"data":[],"nextCursor":"next"}).next_cursor,"next")
        for wire in ({}, {"data":None}, {"data":[{"id":"bad"}]}):
            with self.assertRaises(ProtocolDecodeError): ProjectListResponse.from_wire(wire)

if __name__ == "__main__": unittest.main()
