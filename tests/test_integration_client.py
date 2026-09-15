"""Offline orchestration tests using an injected fake process."""
from __future__ import annotations
import json, os, stat, sys, tempfile, threading, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from codex_wsl_rpc.integration import IntegrationAuthorization, ReadOnlyProjectListClient

class _Stream:
    def __init__(self, fd): self.fd=fd
    def fileno(self): return self.fd
    def close(self):
        try: os.close(self.fd)
        except OSError: pass
class FakeProcess:
    def __init__(self, responses):
        ir, iw=os.pipe(); or_, ow=os.pipe(); er, ew=os.pipe()
        self.stdin,self.stdout,self.stderr=_Stream(iw),_Stream(or_),_Stream(er); self.returncode=0; self.requests=[]
        os.close(ew)
        def server():
            source=os.fdopen(ir,"rb",buffering=0); sink=os.fdopen(ow,"wb",buffering=0)
            response_index=0
            while response_index < len(responses):
                request=json.loads(source.readline()); self.requests.append(request)
                if "id" in request:
                    sink.write(json.dumps(responses[response_index]).encode()+b"\n")
                    response_index += 1
            source.close(); sink.close()
        self.thread=threading.Thread(target=server); self.thread.start()
    def wait(self,timeout): self.thread.join(timeout); return 0
    def terminate(self): pass
    def kill(self): pass

def project(name="secret", roots=None):
    return {"id":"private-id","name":name,"roots":roots or [],"metadata":{"secret":"value"},"position":1,"createdAt":2,"updatedAt":3,"recencyAt":None}

class ClientTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); root=Path(self.temp.name); self.exe=root/"codex-native"; self.exe.write_bytes(b"\x7fELFfake"); self.exe.chmod(stat.S_IRUSR|stat.S_IWUSR|stat.S_IXUSR); self.home=root/"home"; self.home.mkdir()
    def tearDown(self): self.temp.cleanup()
    def _run(self,data,next_cursor=None):
        fake=FakeProcess([{"id":1,"result":{"userAgent":"private","codexHome":"/private","platformFamily":"unix","platformOs":"linux"}}, {"id":2,"result":{"data":data,"nextCursor":next_cursor}}])
        client=ReadOnlyProjectListClient(executable_path=self.exe,home_path=self.home,authorization=IntegrationAuthorization.READ_ONLY_PROJECT_LIST,_popen=lambda *a,**k: fake)
        return client.list_one_page(),fake
    def test_success_exact_sequence_and_safe_summary(self):
        result,fake=self._run([project(roots=[{"path":"/home/person/private"}])],"raw-cursor")
        self.assertEqual([r.get("method") for r in fake.requests],["initialize","initialized","project/list"])
        self.assertEqual([r.get("id") for r in fake.requests],[1,None,2]); self.assertTrue(fake.requests[0]["params"]["capabilities"]["experimentalApi"])
        self.assertEqual(fake.requests[2]["params"],{"cursor":None,"limit":25,"sortKey":"position","sortDirection":"asc"})
        safe=json.dumps(result.summary.to_safe_dict()); self.assertNotIn("secret",safe); self.assertNotIn("private-id",safe); self.assertNotIn("raw-cursor",safe)
        self.assertEqual(result.summary.returned_page_count,1); self.assertTrue(result.summary.has_more)
    def test_empty_page(self):
        result,_=self._run([]); self.assertEqual(result.summary.returned_page_count,0); self.assertFalse(result.summary.has_more)

if __name__ == "__main__": unittest.main()
