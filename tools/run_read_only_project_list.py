#!/usr/bin/env python3
"""Explicit operator entry point; never imported or run by canonical tests."""
from __future__ import annotations
import argparse, json
from pathlib import Path
import sys

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from codex_wsl_rpc.integration import IntegrationAuthorization, IntegrationError, ReadOnlyProjectListClient

def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--i-understand-this-starts-codex", action="store_true", required=True)
    parser.add_argument("--codex-executable", type=Path, required=True)
    parser.add_argument("--home", type=Path, required=True, help="Exact WSL home used by the reviewed product execution")
    args=parser.parse_args()
    try:
        result=ReadOnlyProjectListClient(executable_path=args.codex_executable,home_path=args.home,authorization=IntegrationAuthorization.READ_ONLY_PROJECT_LIST).list_one_page()
    except IntegrationError as error:
        print(json.dumps({"status":"failed","category":error.category}))
        return 1
    print(json.dumps(result.summary.to_safe_dict(),sort_keys=True))
    return 0

if __name__ == "__main__": raise SystemExit(main())
