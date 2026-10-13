#!/usr/bin/env python3
"""Download a file with progress, using Python's own HTTP stack.

curl on this host (MSYS + native Windows curl) failed with error 23 on write
for a 175 MB download while 100 GB was free, so this uses urllib and a plain
binary write, which sidesteps the path/handle problem entirely.

    python tool/download_file.py <url> <dest> [--expect-bytes N]
"""

from __future__ import annotations

import argparse
import sys
import time
import urllib.request
from pathlib import Path

UA = "bledi.tn-station-audit/1.0 (data integrity check)"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("url")
    ap.add_argument("dest")
    ap.add_argument("--expect-bytes", type=int, default=0)
    ap.add_argument("--timeout", type=int, default=1800)
    args = ap.parse_args()

    dest = Path(args.dest)
    dest.parent.mkdir(parents=True, exist_ok=True)

    req = urllib.request.Request(args.url, headers={"User-Agent": UA})
    started = time.time()
    total = 0
    with urllib.request.urlopen(req, timeout=args.timeout) as r:
        declared = int(r.headers.get("Content-Length") or 0)
        print(f"downloading {declared or '?'} bytes -> {dest}", flush=True)
        with dest.open("wb") as fh:
            last = 0.0
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                fh.write(chunk)
                total += len(chunk)
                now = time.time()
                if now - last > 5:
                    last = now
                    pct = f" ({total * 100 // declared}%)" if declared else ""
                    print(f"  {total / 1e6:7.1f} MB{pct}", flush=True)

    elapsed = time.time() - started
    print(f"\nwrote {dest} — {total} bytes in {elapsed:.0f}s")

    if declared and total != declared:
        print(f"FAILED: got {total} of {declared} declared bytes (truncated)")
        return 1
    if args.expect_bytes and total != args.expect_bytes:
        print(f"FAILED: expected {args.expect_bytes} bytes, got {total}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
