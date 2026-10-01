#!/usr/bin/env python3
"""Serve the built Flutter web app together with a same-origin API proxy.

Why this exists: the BLEDI.TN backend does not emit CORS headers, so a browser
cannot call `http://localhost:8000` from a page served on another port. That
blocks the *web* target only — Android/iOS are unaffected because they are not
subject to CORS.

Serving both from one origin removes the restriction without changing the
backend or the app's base URL:

    http://127.0.0.1:8080/            -> the Flutter web build
    http://127.0.0.1:8080/api/v1/...  -> proxied to the backend

The proxy is deliberately minimal and local-only: it forwards GET requests,
copies query strings, and refuses to bind anything but the loopback interface.
It adds the Access-Control-Allow-Origin header so a direct cross-origin call
works too.

Usage:
    python tool/serve_web.py --backend http://localhost:8000 --port 8080
"""

from __future__ import annotations

import argparse
import functools
import http.server
import os
import socketserver
import urllib.error
import urllib.request

DEFAULT_BACKEND = "http://localhost:8000"
DEFAULT_WEB_ROOT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "build",
    "web",
)


class Handler(http.server.SimpleHTTPRequestHandler):
    """Static files from the web build, plus a read-only /api proxy."""

    backend = DEFAULT_BACKEND

    def do_GET(self) -> None:  # noqa: N802 (stdlib naming)
        if self.path.startswith("/api/"):
            self._proxy()
        else:
            super().do_GET()

    def _proxy(self) -> None:
        url = f"{self.backend}{self.path}"
        request = urllib.request.Request(url, headers={"User-Agent": "bledi-web-proxy"})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = response.read()
                content_type = response.headers.get(
                    "Content-Type", "application/json"
                )
                status = response.status
        except urllib.error.HTTPError as exc:
            body = exc.read()
            content_type = exc.headers.get("Content-Type", "application/json")
            status = exc.code
        except Exception as exc:  # backend down, DNS, timeout…
            body = f'{{"error": "proxy failed: {exc}"}}'.encode()
            content_type = "application/json"
            status = 502

        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def end_headers(self) -> None:
        # Never let a stale build be served after a rebuild.
        self.send_header("Cache-Control", "no-store, max-age=0")
        super().end_headers()

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        print(f"[proxy] {fmt % args}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", default=DEFAULT_BACKEND)
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--root", default=DEFAULT_WEB_ROOT)
    args = parser.parse_args()

    if not os.path.isdir(args.root):
        raise SystemExit(
            f"No web build at {args.root}\n"
            "Run: flutter build web --dart-define=BLED_API_BASE=$BACKEND"
        )

    Handler.backend = args.backend.rstrip("/")
    handler = functools.partial(Handler, directory=args.root)

    class Server(socketserver.ThreadingTCPServer):
        allow_reuse_address = True
        daemon_threads = True

    with Server(("127.0.0.1", args.port), handler) as httpd:
        print(f"Serving {args.root}")
        print(f"  app     http://127.0.0.1:{args.port}/")
        print(f"  api     http://127.0.0.1:{args.port}/api/v1/... -> {Handler.backend}")
        print("Ctrl+C to stop.")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nstopped")


if __name__ == "__main__":
    main()