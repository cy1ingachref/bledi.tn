#!/usr/bin/env python3
"""Report which tracked code/config references each file under data/.

This is a read-only audit used by the M2 cleanup. For every tracked file in
data/, it searches the runtime/repo paths (services/, tests/, .github/, k8s/,
docker-compose.yml, apps/web-react/, tool/, e2e/, scripts/) for the file's
basename and prints the referencing files. Files with zero references outside
archive/ are flagged.

Usage: python scripts/audit_data_usage.py [--json]
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SEARCH_PATHS = (
    "services/", "tests/", ".github/", "k8s/", "docker-compose.yml",
    "apps/web-react/", "tool/", "e2e/", "scripts/",
)


def git_ls_files(prefix: str) -> list[str]:
    out = subprocess.run(
        ["git", "-c", "core.quotePath=false", "ls-files", "-z", prefix],
        cwd=REPO, capture_output=True, check=True,
    )
    return [p.decode("utf-8", "surrogateescape") for p in out.stdout.split(b"\0") if p]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true", help="emit JSON instead of text")
    args = ap.parse_args()

    data_files = git_ls_files("data/")
    search_files = []
    for p in SEARCH_PATHS:
        if p.endswith("/"):
            search_files.extend(git_ls_files(p))
        else:
            out = subprocess.run(
                ["git", "-c", "core.quotePath=false", "ls-files", "-z", p],
                cwd=REPO, capture_output=True, check=True,
            )
            paths = [x.decode("utf-8", "surrogateescape") for x in out.stdout.split(b"\0") if x]
            search_files.extend(paths)

    contents: dict[str, str] = {}
    for rel in set(search_files):
        full = REPO / rel
        if not full.is_file():
            continue
        try:
            contents[rel] = full.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue

    results = []
    for rel in data_files:
        basename = Path(rel).name
        refs = [src for src, text in contents.items() if basename in text]
        results.append({"file": rel, "size": (REPO / rel).stat().st_size, "refs": refs})

    unreferenced = [r for r in results if not r["refs"]]

    if args.json:
        print(json.dumps({"files": results, "unreferenced": [r["file"] for r in unreferenced]}, indent=2))
    else:
        for r in results:
            print(f"{r['file']}  ({r['size']:,} bytes)")
            for ref in r["refs"]:
                print(f"    <- {ref}")
        print(f"\nUnreferenced data files: {len(unreferenced)}")
        for r in unreferenced:
            print(f"  {r['file']}  ({r['size']:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
