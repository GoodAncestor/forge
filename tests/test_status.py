import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from forge import config, status


@pytest.fixture
def capture_server():
    """Local HTTP server capturing POSTs; yields (url, received_list)."""
    received = []

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            received.append({
                "path": self.path,
                "auth": self.headers.get("Authorization"),
                "body": json.loads(self.rfile.read(n)),
            })
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok": true}')

        def log_message(self, *args):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{srv.server_port}", received
    srv.shutdown()


def test_noop_when_secret_unset(monkeypatch):
    monkeypatch.setattr(config, "LEASE_SECRET", "")
    # requests must not even be attempted
    import requests

    monkeypatch.setattr(
        requests,
        "post",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError),
    )
    assert status.enabled() is False
    assert status.post("fetch", "x", "fetching") is False


def test_posts_versioned_doc_with_bearer(monkeypatch, capture_server):
    url, received = capture_server
    monkeypatch.setattr(config, "FLEET_URL", url)
    monkeypatch.setattr(config, "LEASE_SECRET", "s3cret")
    ok = status.post("fetch", "gutenberg-mirror", "fetching", {"bytes": 5})
    assert ok is True
    assert len(received) == 1
    response = received[0]
    assert response["path"] == "/forge/status"
    assert response["auth"] == "Bearer s3cret"
    body = response["body"]
    assert body["v"] == 1 and body["kind"] == "fetch"
    assert body["id"] == "gutenberg-mirror" and body["state"] == "fetching"
    assert body["payload"] == {"bytes": 5}
    assert isinstance(body["host"], str) and body["host"]
    assert body["ts"].endswith("Z")


def test_connection_error_swallowed(monkeypatch):
    monkeypatch.setattr(config, "FLEET_URL", "http://127.0.0.1:1")  # closed port
    monkeypatch.setattr(config, "LEASE_SECRET", "s3cret")
    assert status.post("run", "r1", "running") is False  # no exception
