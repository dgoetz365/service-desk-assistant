import http.client
import json
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from service_assistant.assistant import Assistant
from service_assistant.providers import OllamaProvider, ProviderError
from service_assistant.server import make_server


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = make_server(Assistant(), port=0)
        cls.port = cls.server.server_port
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def request(self, method="GET", path="/api/config", body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        try:
            conn.request(method, path, body=body, headers=headers or {})
            response = conn.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            conn.close()

    def post(self, payload=None, extra_headers=None, raw=None):
        _, _, config = self.request()
        token = json.loads(config)["csrf_token"]
        headers = {"Content-Type": "application/json", "X-CSRF-Token": token,
                   "Origin": f"http://127.0.0.1:{self.port}"}
        headers.update(extra_headers or {})
        body = raw if raw is not None else json.dumps(payload or {"question": "Can I collect R-1043?", "mode": "offline"})
        return self.request("POST", "/api/ask", body, headers)

    def test_real_http_offline_request(self):
        status, headers, body = self.post()
        data = json.loads(body)
        self.assertEqual(status, 200)
        self.assertEqual(data["status"], "complete")
        self.assertEqual(data["mode"], "offline")
        self.assertTrue(data["draft"])
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        self.assertNotIn("Access-Control-Allow-Origin", headers)

    def test_static_assets_and_safe_paths(self):
        for path in ["/", "/app.css", "/app.js"]:
            with self.subTest(path=path):
                status, headers, body = self.request(path=path)
                self.assertEqual(status, 200)
                self.assertGreater(len(body), 100)
                self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        for path in ["/../app.py", "/%2e%2e/app.py", "/service_assistant/fixtures.py", "/.env", "/?x=1"]:
            with self.subTest(path=path):
                self.assertEqual(self.request(path=path)[0], 404)

    def test_host_origin_token_and_fetch_site(self):
        self.assertEqual(self.request(headers={"Host": "attacker.invalid"})[0], 403)
        for overrides in [{"Origin": "http://attacker.invalid"}, {"X-CSRF-Token": "bad"},
                          {"X-CSRF-Token": "café"},
                          {"Sec-Fetch-Site": "cross-site"}, {"Sec-Fetch-Site": "same-site"}]:
            with self.subTest(headers=overrides):
                self.assertEqual(self.post(extra_headers=overrides)[0], 403)
        self.assertEqual(self.request("OPTIONS", "/api/ask")[0], 405)

    def test_bad_json_unknown_fields_and_body_limit(self):
        for raw in ["{", '{"question":"ok","mode":"offline","send":true}',
                    '{"question":42,"mode":"offline"}',
                    '{"question":"a","question":"b","mode":"offline"}',
                    '{"question":"\\ud800","mode":"offline"}',
                    '{"question":"hello","mode":"\\ud800"}',
                    json.dumps({"question": "x" * 1001, "mode": "offline"})]:
            with self.subTest(raw=raw[:40]):
                self.assertEqual(self.post(raw=raw)[0], 400)
        self.assertEqual(self.post(raw="x" * 9000)[0], 413)
        self.assertEqual(self.post(extra_headers={"Content-Length": "9" * 5000})[0], 413)
        self.assertEqual(self.post(extra_headers={"Content-Type": "text/plain"})[0], 415)

    def test_duplicate_headers_are_rejected(self):
        for name in ("Host", "Origin", "Content-Length"):
            with self.subTest(header=name):
                conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
                try:
                    conn.putrequest("GET", "/api/config", skip_host=True)
                    conn.putheader("Host", f"127.0.0.1:{self.port}")
                    if name != "Host":
                        conn.putheader(name, "0")
                    conn.putheader(name, "0")
                    conn.endheaders()
                    response = conn.getresponse()
                    self.assertEqual(response.status, 400)
                    response.read()
                finally:
                    conn.close()

    def test_early_rejection_delivers_json_after_bounded_body_drain(self):
        body = "x" * 8192
        for headers in ({"Host": "attacker.invalid"}, {"Origin": "http://attacker.invalid"},
                        {"X-CSRF-Token": "bad"}):
            with self.subTest(headers=headers):
                for _ in range(3):
                    status, _, raw = self.post(raw=body, extra_headers=headers)
                    self.assertEqual(status, 403)
                    self.assertIn("error", json.loads(raw))
        status, _, raw = self.post(raw="x" * 12000)
        self.assertEqual(status, 413)
        self.assertIn("error", json.loads(raw))
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        try:
            started = time.monotonic()
            conn.putrequest("POST", "/api/ask")
            conn.putheader("Content-Length", "1000")
            conn.endheaders()  # Invalid token and a body that never arrives.
            response = conn.getresponse()
            self.assertEqual(response.status, 403)
            self.assertIn("error", json.loads(response.read()))
            self.assertLess(time.monotonic() - started, 2)
        finally:
            conn.close()

    def test_health_is_not_model_readiness(self):
        status, _, body = self.request(path="/api/health")
        self.assertEqual(status, 200)
        self.assertIn("model availability is not checked", json.loads(body)["scope"])


class OllamaHTTPStubTests(unittest.TestCase):
    def test_transport_uses_actual_chat_endpoint(self):
        received = []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                body = self.rfile.read(int(self.headers["Content-Length"]))
                received.append((self.path, json.loads(body)))
                output = json.dumps({"done": True, "message": {"role": "assistant", "content": "{}"}}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(output)))
                self.end_headers()
                self.wfile.write(output)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            provider = OllamaProvider(base_url=f"http://127.0.0.1:{server.server_port}")
            output = provider.chat([{"role": "user", "content": "test"}], [])
            self.assertEqual(output["content"], "{}")
            self.assertEqual(received[0][0], "/api/chat")
            self.assertEqual(received[0][1]["model"], "qwen3:4b")
            self.assertFalse(received[0][1]["stream"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
