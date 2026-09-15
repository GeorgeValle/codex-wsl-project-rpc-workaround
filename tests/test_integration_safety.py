"""Static and inertness guards for the separately gated integration."""
from __future__ import annotations
import argparse, ast, importlib.util, os, subprocess, sys, unittest
from pathlib import Path
from unittest import mock
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
        path=ROOT/"tools/run_read_only_project_list.py"; spec=importlib.util.spec_from_file_location("inert_runner",path); module=importlib.util.module_from_spec(spec)
        with mock.patch.object(argparse.ArgumentParser,"parse_args",side_effect=AssertionError("parsed")), mock.patch.object(subprocess,"Popen",side_effect=AssertionError("spawned")), mock.patch.object(os,"getenv",side_effect=AssertionError("environment read")):
            spec.loader.exec_module(module)
        self.assertEqual(module.REPOSITORY_ROOT, ROOT)
    def test_runner_bootstraps_src_in_isolated_checkout_import(self):
        runner=ROOT/"tools/run_read_only_project_list.py"
        code=("import importlib.util; p="+repr(str(runner))+"; "
              "s=importlib.util.spec_from_file_location('checkout_runner',p); "
              "m=importlib.util.module_from_spec(s); s.loader.exec_module(m); "
              "assert str(m.REPOSITORY_ROOT/'src') == __import__('sys').path[0]")
        completed=subprocess.run([sys.executable,"-I","-c",code],cwd="/",check=False,capture_output=True,text=True)
        self.assertEqual(completed.returncode,0,completed.stderr)
    def test_runner_requires_both_authorization_and_executable(self):
        path=ROOT/"tools/run_read_only_project_list.py"; spec=importlib.util.spec_from_file_location("gated_runner",path); module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        for argv in (["runner","--codex-executable","/fake","--home","/fake"],
                     ["runner","--i-understand-this-starts-codex","--home","/fake"]):
            with self.subTest(argv=argv), mock.patch.object(sys,"argv",argv), mock.patch("codex_wsl_rpc.integration.client.subprocess.Popen",side_effect=AssertionError("spawned")):
                with self.assertRaises(SystemExit): module.main()
    def test_runner_not_referenced_by_tests(self):
        references=[]
        for path in (ROOT/"tests").glob("test_*.py"):
            if path.name != self_path and "run_read_only_project_list.py" in path.read_text(): references.append(path.name)
        self.assertEqual(references,[])

self_path=Path(__file__).name
if __name__ == "__main__": unittest.main()
