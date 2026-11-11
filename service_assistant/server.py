"""Loopback-only development server. No business data is persisted."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import secrets
import threading
import time

from .providers import parse_json

STATIC = Path(__file__).resolve().parent / "static"
ROUTES = {"/": ("index.html", "text/html; charset=utf-8"),
          "/app.css": ("app.css", "text/css; charset=utf-8"),
          "/app.js": ("app.js", "text/javascript; charset=utf-8")}


def make_server(assistant, port=8765):
    token = secrets.token_urlsafe(32)
    slots = threading.BoundedSemaphore(2)

    class Handler(BaseHTTPRequestHandler):
        server_version = "LocalRepairDemo"
        sys_version = ""

        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def log_message(self, format, *args):
            # Do not log user questions, records, or CSRF tokens.
            pass

        def _reply(self, status, body, content_type="application/json; charset=utf-8"):
            if status >= 400:
                self._discard_rejected_body()
            if not isinstance(body, bytes):
                body = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'")
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def _discard_rejected_body(self):
            # A close with unread POST bytes can reset the socket on Windows,
            # hiding the JSON error. Drain only unambiguous framing, bounded
            # by both bytes and a total deadline; never parse or execute it.
            if self.command != "POST" or getattr(self, "_body_read", False):
                return
            lengths = self.headers.get_all("Content-Length", [])
            if len(lengths) != 1 or self.headers.get("Transfer-Encoding"):
                return
            length = lengths[0]
            if not length.isascii() or not length.isdecimal() or len(length) > 6:
                return
            remaining = int(length)
            if remaining > 65536:
                return
            deadline = time.monotonic() + 0.1
            previous_timeout = self.connection.gettimeout()
            try:
                while remaining and time.monotonic() < deadline:
                    self.connection.settimeout(max(0.001, deadline - time.monotonic()))
                    chunk = self.rfile.read1(min(remaining, 8192))
                    if not chunk:
                        break
                    remaining -= len(chunk)
            except OSError:
                pass
            finally:
                self._body_read = True
                self.connection.settimeout(previous_timeout)

        def _host_ok(self):
            for header in ("Host", "Origin", "Content-Length", "Content-Type", "X-CSRF-Token", "Sec-Fetch-Site", "Transfer-Encoding"):
                if len(self.headers.get_all(header, [])) > 1:
                    self._reply(400, {"error": "Duplicate request headers are not supported."})
                    return False
            allowed = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
            if self.headers.get("Host") not in allowed:
                self._reply(403, {"error": "Use the loopback URL printed by the server."})
                return False
            return True

        def do_GET(self):
            if not self._host_ok():
                return
            if self.path == "/api/config":
                self._reply(200, {"csrf_token": token, "model": assistant.provider.model if assistant.provider else None,
                                  "timeout": assistant.provider.timeout if assistant.provider else None,
                                  "max_rounds": assistant.max_rounds, "synthetic": True})
            elif self.path == "/api/health":
                self._reply(200, {"status": "ok", "scope": "local app only; model availability is not checked"})
            elif self.path in ROUTES:
                name, mime = ROUTES[self.path]
                self._reply(200, (STATIC / name).read_bytes(), mime)
            else:
                self._reply(404, {"error": "Route not found."})

        def do_POST(self):
            if not self._host_ok():
                return
            if self.path != "/api/ask":
                self._reply(404, {"error": "Route not found."})
                return
            origin = self.headers.get("Origin")
            supplied_token = self.headers.get("X-CSRF-Token", "")
            expected_origin = "http://" + self.headers.get("Host", "")
            if ((origin is not None and origin != expected_origin)
                    or self.headers.get("Sec-Fetch-Site", "same-origin") not in {"none", "same-origin"}
                    or not supplied_token.isascii()
                    or not secrets.compare_digest(supplied_token, token)):
                self._reply(403, {"error": "Request origin or token is invalid. Reload the local page."})
                return
            if self.headers.get_content_type() != "application/json" or self.headers.get("Transfer-Encoding"):
                self._reply(415, {"error": "Send a fixed-length application/json request."})
                return
            length = self.headers.get("Content-Length", "")
            if not length.isascii() or not length.isdecimal() or len(length) > 5 or not 1 <= int(length) <= 8192:
                self._reply(413, {"error": "Request body must be between 1 and 8,192 bytes."})
                return
            try:
                self._body_read = True
                raw = self.rfile.read(int(length))
                if len(raw) != int(length):
                    raise ValueError("Truncated request body")
                payload = parse_json(raw.decode("utf-8"))
                if not isinstance(payload, dict) or set(payload) != {"question", "mode"}:
                    raise ValueError("Supply question and mode only.")
                if not isinstance(payload["question"], str) or not isinstance(payload["mode"], str):
                    raise ValueError("Question and mode must be strings.")
                if not slots.acquire(blocking=False):
                    self._reply(503, {"error": "Two requests are already running. Try again when one finishes."})
                    return
                try:
                    result = assistant.run(payload["question"], payload["mode"])
                finally:
                    slots.release()
                self._reply(200, result)
            except (ValueError, UnicodeError, RecursionError):
                self._reply(400, {"error": "Invalid request. Use a question of 1–1,000 characters and a supported mode."})
            except (TimeoutError, OSError):
                self._reply(408, {"error": "Request timed out. Retry from the local page."})

        def do_OPTIONS(self):
            self._reply(405, {"error": "Cross-origin requests are not supported."})

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)
