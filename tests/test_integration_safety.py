"""Static and inertness guards for the separately gated integration."""
from __future__ import annotations
import ast, importlib.util, sys, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; SRC=ROOT/"src"; sys.path.insert(0,str(SRC))

class SafetyTests(unittest.TestCase):
    def test_no_mutation_network_discovery_or_arbitrary_api(self):
        text="\n".join(p.read_text() for p in (SRC/"codex_wsl_rpc/integration").glob("*.py"))
        for denied in ("project/create","project/update","project/import","project/move","project/delete","socket.","shutil.which","shell=True","CODEX_HOME","sqlite3"):
            self.assertNotIn(denied,text)
        for public in ("call","send_request","send_raw","send_notification"):
            self.assertNotRegex(text,rf"def {public}\(")
    def test_imports_and_runner_are_inert(self):
        import codex_wsl_rpc.integration
        path=ROOT/"tools/run_read_only_project_list.py"; spec=importlib.util.spec_from_file_location("inert_runner",path); module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    def test_runner_not_referenced_by_tests(self):
        references=[]
        for path in (ROOT/"tests").glob("test_*.py"):
            if path.name != self_path and "run_read_only_project_list.py" in path.read_text(): references.append(path.name)
        self.assertEqual(references,[])

self_path=Path(__file__).name
if __name__ == "__main__": unittest.main()
