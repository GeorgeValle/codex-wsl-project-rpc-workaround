from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from codex_wsl_rpc.mock import FakeAppServer  # noqa: E402
from codex_wsl_rpc.protocol import (InitializeCapabilities, Project, ProjectListParams,  # noqa: E402
    ProjectRoot, ProjectSortKey, Request, SortDirection, SuccessResponse)

IDS=[f"00000000-0000-0000-0000-{number:012d}" for number in range(1,130)]
PATHS=("/home/<USER>/project","C:\\Users\\<WINDOWS_USER>\\project","\\\\wsl.localhost\\<DISTRO>\\home\\<USER>\\project","\\\\wsl$\\<DISTRO>\\home\\<USER>\\project")

def project(number, *, position=None, recency=None, paths=None):
    roots=tuple(ProjectRoot(path) for path in (paths or (f"/fixture/{number}",)))
    return Project(IDS[number-1],f"p{number}",roots,{"owner":str(number)},number if position is None else position,1,2,recency)

def listed(projects, params=ProjectListParams()):
    server=FakeAppServer(projects)
    server.handle(Request(1,"initialize",{"clientInfo":{"name":"n","version":"1"},"capabilities":InitializeCapabilities(True).to_wire()}))
    return server.handle(Request(2,"project/list",params.to_wire()))

def ids(response): return [item["id"] for item in response.result["data"]]


class ProjectListTests(unittest.TestCase):
    def test_empty_one_and_position_orders(self):
        self.assertEqual(ids(listed([])),[])
        fixtures=[project(3,position=1),project(2,position=1),project(1,position=2)]
        self.assertEqual(ids(listed(fixtures)),[IDS[1],IDS[2],IDS[0]])
        desc=ProjectListParams(sort_key=ProjectSortKey.POSITION,sort_direction=SortDirection.DESC)
        self.assertEqual(ids(listed(fixtures,desc)),[IDS[0],IDS[2],IDS[1]])

    def test_recency_nulls_last_both_directions(self):
        fixtures=[project(1,recency=20),project(2,recency=10),project(3,recency=10),project(4),project(5)]
        asc=ProjectListParams(sort_key=ProjectSortKey.RECENCY_AT,sort_direction=SortDirection.ASC)
        desc=ProjectListParams(sort_key=ProjectSortKey.RECENCY_AT,sort_direction=SortDirection.DESC)
        self.assertEqual(ids(listed(fixtures,asc)),[IDS[1],IDS[2],IDS[0],IDS[3],IDS[4]])
        self.assertEqual(ids(listed(fixtures,desc)),[IDS[0],IDS[2],IDS[1],IDS[4],IDS[3]])
        default=ProjectListParams(sort_key=ProjectSortKey.RECENCY_AT)
        self.assertEqual(ids(listed(fixtures,default)),ids(listed(fixtures,desc)))

    def test_limits(self):
        fixtures=[project(i) for i in range(1,120)]
        expected={None:25,0:1,1:1,25:25,100:100,101:100,2**32-1:100}
        for limit,count in expected.items():
            with self.subTest(limit=limit): self.assertEqual(len(ids(listed(fixtures,ProjectListParams(limit=limit)))),count)

    def test_direction_without_key(self):
        response=listed([],ProjectListParams(sort_direction=SortDirection.ASC))
        self.assertEqual((response.error.code,response.error.message),(-32602,"sortDirection requires sortKey"))

    def test_paths_roots_and_metadata_preserved(self):
        fixture=project(1,paths=PATHS); response=listed([fixture]); wire=response.result["data"][0]
        self.assertEqual([root["path"] for root in wire["roots"]],list(PATHS)); self.assertEqual(wire["metadata"],{"owner":"1"})

    def test_cursor_formats_and_multiple_pages(self):
        fixtures=[project(i,recency=None if i>=4 else i) for i in range(1,7)]
        first=listed(fixtures,ProjectListParams(limit=2)); self.assertEqual(first.result["nextCursor"],f"2|{IDS[1]}")
        second=listed(fixtures,ProjectListParams(limit=2,cursor=first.result["nextCursor"])); self.assertEqual(ids(second),[IDS[2],IDS[3]])
        final=listed(fixtures,ProjectListParams(limit=2,cursor=second.result["nextCursor"])); self.assertIsNone(final.result["nextCursor"])
        desc=ProjectListParams(limit=1,sort_key=ProjectSortKey.POSITION,sort_direction=SortDirection.DESC)
        self.assertEqual(listed(fixtures,desc).result["nextCursor"],f"v1|position|desc|6|{IDS[5]}")
        rec=ProjectListParams(limit=4,sort_key=ProjectSortKey.RECENCY_AT,sort_direction=SortDirection.ASC)
        self.assertEqual(listed(fixtures,rec).result["nextCursor"],f"v1|recencyAt|asc|null|{IDS[3]}")

    def test_negative_position_cursors_round_trip_and_paginate(self):
        fixtures=[project(1,position=-8),project(2,position=-7),project(3,position=-6),project(4,position=-5)]
        first=listed(fixtures,ProjectListParams(limit=2))
        self.assertEqual(ids(first),IDS[:2])
        self.assertEqual(first.result["nextCursor"],f"-7|{IDS[1]}")
        second=listed(fixtures,ProjectListParams(limit=2,cursor=first.result["nextCursor"]))
        self.assertEqual(ids(second),IDS[2:4])
        self.assertIsNone(second.result["nextCursor"])

        desc=ProjectListParams(limit=2,sort_key=ProjectSortKey.POSITION,sort_direction=SortDirection.DESC)
        first_desc=listed(fixtures,desc)
        self.assertEqual(first_desc.result["nextCursor"],f"v1|position|desc|-6|{IDS[2]}")
        second_desc=listed(fixtures,ProjectListParams(
            cursor=first_desc.result["nextCursor"],limit=2,
            sort_key=desc.sort_key,sort_direction=desc.sort_direction,
        ))
        self.assertEqual(ids(second_desc),[IDS[1],IDS[0]])

    def test_position_cursor_signed_i64_boundaries(self):
        accepted=[-(2**63),2**63-1]
        for value in accepted:
            with self.subTest(value=value):
                response=listed([project(1)],ProjectListParams(cursor=f"{value}|{IDS[0]}"))
                self.assertIsInstance(response,SuccessResponse)

        rejected=[-(2**63)-1,2**63,"+1","01","-0"]
        for value in rejected:
            with self.subTest(value=value):
                response=listed([project(1)],ProjectListParams(cursor=f"{value}|{IDS[0]}"))
                self.assertEqual(response.error.code,-32602)

    def test_pagination_crosses_to_and_anchors_in_nulls(self):
        fixtures=[project(1,recency=1),project(2,recency=2),project(3),project(4),project(5)]
        base=ProjectListParams(limit=3,sort_key=ProjectSortKey.RECENCY_AT,sort_direction=SortDirection.ASC)
        first=listed(fixtures,base); self.assertEqual(ids(first),IDS[:3])
        cursor=first.result["nextCursor"]
        self.assertEqual(ids(listed(fixtures,ProjectListParams(cursor=cursor,limit=3,sort_key=base.sort_key,sort_direction=base.sort_direction))),IDS[3:5])

    def test_cursor_validation(self):
        letter_uuid="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        bad=["x"*129,"1|x|extra","v2|position|desc|1|"+IDS[0],"v1|recencyAt|desc|1|"+IDS[0],
             "one|"+IDS[0],"1|"+letter_uuid.upper(),"1|bad"]
        for cursor in bad:
            with self.subTest(cursor=cursor):
                response=listed([project(1)],ProjectListParams(cursor=cursor)); self.assertEqual(response.error.code,-32602)

    def test_cursor_mismatch_and_invalid_recency(self):
        cases=[ProjectListParams(cursor=f"v1|position|desc|1|{IDS[0]}",sort_key=ProjectSortKey.POSITION,sort_direction=SortDirection.ASC),
               ProjectListParams(cursor=f"v1|recencyAt|asc|wat|{IDS[0]}",sort_key=ProjectSortKey.RECENCY_AT,sort_direction=SortDirection.ASC)]
        for params in cases: self.assertEqual(listed([project(1)],params).error.code,-32602)

    def test_absent_anchor_and_repeat_are_stateless(self):
        fixtures=[project(1),project(3)]
        params=ProjectListParams(cursor=f"2|{IDS[1]}",limit=5)
        self.assertEqual(ids(listed(fixtures,params)),[IDS[2]])
        self.assertEqual(listed(fixtures,params).to_wire(),listed(fixtures,params).to_wire())

    def test_snapshot_and_response_isolation(self):
        roots=[ProjectRoot("/original")]; metadata={"a":"1"}
        fixture=Project(IDS[0],"p",roots,metadata,1,1,1,None); server=FakeAppServer([fixture])
        roots.append(ProjectRoot("/later")); metadata["a"]="changed"
        server.handle(Request(1,"initialize",{"clientInfo":{"name":"n","version":"1"},"capabilities":{"experimentalApi":True}}))
        first=server.handle(Request(2,"project/list",{})); first.result["data"][0]["metadata"]["a"]="mutated"
        second=server.handle(Request(3,"project/list",{})); self.assertEqual(second.result["data"][0]["metadata"],{"a":"1"})

    def test_store_uuid_constraint_does_not_tighten_schema(self):
        broad=Project("broader-id","p",(),{},0,0,0)
        self.assertEqual(broad.id,"broader-id")
        with self.assertRaises(ValueError): FakeAppServer([broad])

if __name__ == "__main__": unittest.main()
