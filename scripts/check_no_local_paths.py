#!/usr/bin/env python3
"""Fail if a hard-coded local Windows user path appears in tracked code/docs.

Usage: python scripts/check_no_local_paths.py [path ...]

Default: scan the whole repo's tracked files. Excludes `archive/`, `data/`
(provenance strings there are intentional and pinned by verify_seed.py), binary
files, and this script itself (it names the forbidden pattern to detect it).
CI: add as a step in data-pipeline.yml after the seed check.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
# Deliberately constructed so this file does not match itself.
PATTERN = re.compile(r"C:[/\\]Users[/\\]")
EXCLUDED_PREFIXES = ("archive/", "data/", "scripts/check_no_local_paths.py")


def tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True
    )
    return [line for line in out.stdout.splitlines() if line]


def main(paths: list[str] | None = None) -> int:
    files = paths if paths else tracked_files()
    offenders: list[str] = []
    for rel in files:
        if any(rel.startswith(prefix) for prefix in EXCLUDED_PREFIXES):
            continue
        full = REPO / rel
        if not full.is_file():
            continue
        try:
            text = full.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # skip binaries
        for lineno, line in enumerate(text.splitlines(), 1):
            if PATTERN.search(line):
                offenders.append(f"{rel}:{lineno}: {line.strip()[:140]}")
    if offenders:
        print("FAIL: hard-coded local user paths found in tracked code/docs:")
        print("\n".join(offenders[:80]))
        print(f"({len(offenders)} total)")
        return 1
    print("OK: no hard-coded local user paths in tracked code/docs")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
