import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MOCK = ROOT / "src/codex_wsl_rpc/mock"


class TrustedDevelopmentSafetyGuards(unittest.TestCase):
    """Static regression guards, not OS-level security containment."""
    def test_runtime_has_no_forbidden_imports_or_operations(self):
        forbidden_imports={"subprocess","socket","sqlite3","asyncio","threading","requests","http","urllib","websocket"}
        forbidden_text=(".codex","os.environ","getenv(","Path.exists","Path.resolve","pathlib","Popen(","project/create","project/update","project/import","project/move","project/delete")
        for path in MOCK.glob("*.py"):
            source=path.read_text(encoding="utf-8"); tree=ast.parse(source)
            imports={node.names[0].name.split('.')[0] for node in ast.walk(tree) if isinstance(node,ast.Import)}
            imports|={node.module.split('.')[0] for node in ast.walk(tree) if isinstance(node,ast.ImportFrom) and node.module}
            self.assertFalse(imports & forbidden_imports,(path,imports & forbidden_imports))
            for marker in forbidden_text: self.assertNotIn(marker,source,path)

if __name__ == "__main__": unittest.main()
