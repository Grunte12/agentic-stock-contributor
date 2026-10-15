"""Localhost HTTP bridge for the extension. Long-poll for jobs, post results. Token + extension origin required."""
import hashlib
import hmac
import json
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

MAX_BODY = 8 * 1024 * 1024


def load_token(data_dir):
    p = Path(data_dir) / "token"
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(secrets.token_urlsafe(24))
        p.chmod(0o600)
    return p.read_text().strip()


class Bridge:
    def __init__(self, queue, token, host="127.0.0.1", port=8777, poll_seconds=20, dashboard=None):
        self.queue, self.token, self.poll_seconds = queue, token, poll_seconds
        self.dashboard = dashboard  # callable returning the page HTML, or None
        # read-only link token: it opens the dashboard but cannot pair an extension or post results
        self.dash_token = hmac.new(token.encode(), b"dashboard", hashlib.sha256).hexdigest()[:32]
        self.last_seen = None
        self.ext_version = None
        bridge = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _ok(self):
                if self.headers.get("Host", "") not in bridge.hosts:
                    self._send(403, {"error": "host"})
                    return False
                origin = self.headers.get("Origin")
                if origin and not origin.startswith("chrome-extension://"):
                    self._send(403, {"error": "origin"})
                    return False
                if not hmac.compare_digest(self.headers.get("X-Intel-Token", ""), bridge.token):
                    self._send(401, {"error": "token"})
                    return False
                bridge.last_seen = time.time()
                bridge.ext_version = self.headers.get("X-Intel-Ext", "")[:16]
                return True

            def _send(self, code, obj):
                b = json.dumps(obj).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)

            def do_OPTIONS(self):
                self.send_response(204)
                self.send_header("Access-Control-Allow-Headers", "X-Intel-Token, X-Intel-Ext, Content-Type")
                self.send_header("Access-Control-Allow-Methods", "GET, POST")
                origin = self.headers.get("Origin", "")
                if origin.startswith("chrome-extension://"):
                    self.send_header("Access-Control-Allow-Origin", origin)
                self.end_headers()

            def _dashboard(self):
                if self.headers.get("Host", "") not in bridge.hosts or self.headers.get("Origin"):
                    return self._send(403, {"error": "host_or_origin"})
                given = parse_qs(urlsplit(self.path).query).get("t", [""])[0]
                if not hmac.compare_digest(given, bridge.dash_token):
                    return self._send(401, {"error": "token"})
                if bridge.dashboard is None:
                    return self._send(404, {"error": "no_dashboard"})
                b = bridge.dashboard().encode()
                self.send_response(200)
                for k, v in (("Content-Type", "text/html; charset=utf-8"), ("Content-Length", str(len(b))), ("Cache-Control", "no-store"),
                             ("Referrer-Policy", "no-referrer"), ("X-Content-Type-Options", "nosniff"),
                             ("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'")):
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(b)

            def _file(self):
                """Raw bytes of one file of the dispatched upload_stage or upload_metadata job, re-hashed against the plan right before sending."""
                q = parse_qs(urlsplit(self.path).query)
                try:
                    f = bridge.queue.stage_file((q.get("job") or [""])[0], int((q.get("i") or ["x"])[0]))
                except ValueError:
                    f = None
                if not f:
                    return self._send(404, {"error": "not_staged"})
                data = Path(f["path"]).read_bytes()
                if hashlib.sha256(data).hexdigest() != f["sha256"]:
                    return self._send(409, {"error": "sha_mismatch"})
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                if urlsplit(self.path).path == "/dashboard":
                    return self._dashboard()
                if not self._ok():
                    return
                if self.path.startswith("/v1/dashboard-url"):
                    return self._send(200, {"url": bridge.dashboard_url()})
                if urlsplit(self.path).path == "/v1/file":
                    return self._file()
                if self.path.startswith("/v1/ping"):
                    return self._send(200, {"ok": True})
                if self.path.startswith("/v1/next"):
                    if bridge.queue.store.get_state("reload_extension"):  # set by `reload-extension`; the extension reloads itself
                        bridge.queue.store.set_state("reload_extension", None)
                        return self._send(200, {"job": None, "reason": "reload", "reload": True})
                    end = time.time() + bridge.poll_seconds
                    while True:
                        job, reason = bridge.queue.next_job()
                        if job or reason.startswith("stopped") or time.time() >= end:
                            return self._send(200, {"job": job, "reason": reason})
                        time.sleep(0.5)
                self._send(404, {"error": "not_found"})

            def do_POST(self):
                if not self._ok():
                    return
                if self.path != "/v1/result":
                    return self._send(404, {"error": "not_found"})
                n = int(self.headers.get("Content-Length", "0"))
                if n <= 0 or n > MAX_BODY:
                    return self._send(413, {"error": "size"})
                try:
                    body = json.loads(self.rfile.read(n))
                    res = bridge.queue.complete(body["job_id"], body["payload"])
                except (KeyError, ValueError, TypeError):
                    return self._send(400, {"error": "bad_request"})
                self._send(200, res)

        self.httpd = ThreadingHTTPServer((host, port), H)
        self.port = self.httpd.server_address[1]
        self.hosts = {f"127.0.0.1:{self.port}", f"localhost:{self.port}"}
        self.thread = None

    def start(self):
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    def dashboard_url(self):
        return f"http://127.0.0.1:{self.port}/dashboard?t={self.dash_token}"

    def connected(self):
        return self.last_seen is not None and time.time() - self.last_seen < 60
