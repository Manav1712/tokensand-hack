#!/usr/bin/env python3
"""Catch-all HTTP server for the jail sink. Logs request bodies to HTTP_LOG."""

from __future__ import annotations

import os
from http.server import BaseHTTPRequestHandler, HTTPServer

HTTP_LOG = os.environ.get("HTTP_LOG", "/var/log/skill-warden-http.log")
LISTEN = os.environ.get("HTTP_LISTEN", "0.0.0.0:80")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, _format: str, *_args) -> None:
        return

    def _handle(self) -> None:
        length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(length) if length else b""
        target = self.path
        if self.command == "POST" and self.path.startswith("http://"):
            target = self.path
        line = f"{self.command} {target}\n{body.decode('utf-8', errors='replace')}\n---\n"
        with open(HTTP_LOG, "a", encoding="utf-8") as log:
            log.write(line)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok":true}')

    def do_GET(self) -> None:
        self._handle()

    def do_POST(self) -> None:
        self._handle()

    def do_CONNECT(self) -> None:
        self._handle()


def main() -> None:
    host, _, port = LISTEN.partition(":")
    server = HTTPServer((host, int(port)), Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
