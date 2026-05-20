from __future__ import annotations

import argparse
import email.utils
import sys
import os
from functools import partial
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path


_src_dir = Path(__file__).resolve().parents[1]   # src/
ROOT_DIR = _src_dir.parent                        # repo root (or package root in a release bundle)
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

from app.api import ApiNotFound, ApiStreamResponse, handle_delete, handle_get, handle_post, handle_put
from app.env import load_env_file
from app.vault import Vault, VaultPathError

WEB_DIR = ROOT_DIR / "web"
FRONTEND_DIST_DIR = _src_dir / "frontend" / "dist"


class LocusStaticHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args: object, static_dir: Path, **kwargs: object) -> None:
        self.static_dir = static_dir
        self.spa_index = static_dir / "index.html"
        super().__init__(*args, directory=str(static_dir), **kwargs)

    def do_GET(self) -> None:
        if self.path.startswith("/api/"):
            self._handle_api_get()
            return
        super().do_GET()

    def do_POST(self) -> None:
        if self.path.startswith("/api/"):
            self._handle_api_post()
            return
        self._send_bytes(404, b'{"error":"not_found"}', "application/json; charset=utf-8")

    def do_PUT(self) -> None:
        if self.path.startswith("/api/"):
            self._handle_api_put()
            return
        self._send_bytes(404, b'{"error":"not_found"}', "application/json; charset=utf-8")

    def do_DELETE(self) -> None:
        if self.path.startswith("/api/"):
            self._handle_api_delete()
            return
        self._send_bytes(404, b'{"error":"not_found"}', "application/json; charset=utf-8")

    def send_head(self):  # type: ignore[no-untyped-def]
        requested_path = self.translate_path(self.path)
        if self.path.startswith("/api/") or Path(requested_path).exists():
            return super().send_head()

        if self.spa_index.exists():
            self.path = "/index.html"
            return super().send_head()

        return super().send_head()

    def end_headers(self) -> None:
        # Static files get no-cache so the browser revalidates via Last-Modified
        # (the base class sends Last-Modified and handles If-Modified-Since automatically).
        # API responses handle Cache-Control themselves in _send_bytes / _send_stream.
        if not self.path.startswith("/api/"):
            self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def _handle_api_get(self) -> None:
        try:
            response = handle_get(self.path, Vault.from_env())
        except VaultPathError as exc:
            self._send_bytes(500, b'{"error":"vault_not_configured"}', "application/json; charset=utf-8")
            return
        except ApiNotFound:
            self._send_bytes(404, b'{"error":"not_found"}', "application/json; charset=utf-8")
            return
        if isinstance(response, ApiStreamResponse):
            self._send_stream(response)
            return
        self._send_bytes(response.status, response.body, response.content_type, response.last_modified)

    def _handle_api_post(self) -> None:
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(content_length)
            response = handle_post(self.path, body, Vault.from_env())
        except VaultPathError:
            self._send_bytes(500, b'{"error":"vault_not_configured"}', "application/json; charset=utf-8")
            return
        except ApiNotFound:
            self._send_bytes(404, b'{"error":"not_found"}', "application/json; charset=utf-8")
            return
        if isinstance(response, ApiStreamResponse):
            self._send_stream(response)
            return
        self._send_bytes(response.status, response.body, response.content_type)

    def _handle_api_put(self) -> None:
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(content_length)
            response = handle_put(self.path, body, Vault.from_env())
        except VaultPathError:
            self._send_bytes(500, b'{"error":"vault_not_configured"}', "application/json; charset=utf-8")
            return
        except ApiNotFound:
            self._send_bytes(404, b'{"error":"not_found"}', "application/json; charset=utf-8")
            return
        self._send_bytes(response.status, response.body, response.content_type)

    def _handle_api_delete(self) -> None:
        try:
            response = handle_delete(self.path, Vault.from_env())
        except VaultPathError:
            self._send_bytes(500, b'{"error":"vault_not_configured"}', "application/json; charset=utf-8")
            return
        except ApiNotFound:
            self._send_bytes(404, b'{"error":"not_found"}', "application/json; charset=utf-8")
            return
        self._send_bytes(response.status, response.body, response.content_type)

    def _send_bytes(
        self, status: int, body: bytes, content_type: str, last_modified: float | None = None
    ) -> None:
        if last_modified is not None:
            ims = self.headers.get("If-Modified-Since", "")
            if ims:
                try:
                    since = email.utils.parsedate_to_datetime(ims).timestamp()
                    if last_modified <= since + 1:
                        self.send_response(304)
                        self.send_header("Cache-Control", "no-cache")
                        self.send_header("Last-Modified", self.date_time_string(int(last_modified)))
                        self.end_headers()
                        return
                except Exception:
                    pass

        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        if last_modified is not None:
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Last-Modified", self.date_time_string(int(last_modified)))
        else:
            self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_stream(self, response: ApiStreamResponse) -> None:
        self.send_response(response.status)
        self.send_header("Content-Type", response.content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        for chunk in response.events:
            self.wfile.write(chunk)
            self.wfile.flush()
        self.close_connection = True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve Locus RP.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", default=8787, type=int)
    parser.add_argument(
        "--static-dir",
        default=None,
        help="Directory for frontend static files. Defaults to LOCUS_STATIC_DIR, frontend/dist when built, then web/.",
    )
    return parser.parse_args()


def choose_static_dir(value: str | None = None) -> Path:
    configured = value or os.environ.get("LOCUS_STATIC_DIR")
    if configured:
        path = Path(configured).expanduser()
        if not path.is_absolute():
            path = ROOT_DIR / path
        return path.resolve()
    if (FRONTEND_DIST_DIR / "index.html").is_file():
        return FRONTEND_DIST_DIR
    return WEB_DIR


def main() -> None:
    load_env_file(ROOT_DIR / ".env")
    args = parse_args()
    static_dir = choose_static_dir(args.static_dir)
    handler = partial(LocusStaticHandler, static_dir=static_dir)
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(
        f"Locus RP listening on http://{args.host}:{args.port} serving {static_dir}",
        flush=True,
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
