import pytest
import requests

from forge import lease


class FakeResp:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))


def make_client(monkeypatch, responses):
    """responses: list of (status, payload) consumed per call; records requests."""
    calls = []

    def fake_post(url, json=None, headers=None, timeout=None):
        calls.append({"url": url, "body": json, "headers": headers})
        return FakeResp(*responses.pop(0))

    def fake_get(url, timeout=None):
        calls.append({"url": url})
        return FakeResp(*responses.pop(0))

    monkeypatch.setattr(lease.requests, "post", fake_post)
    monkeypatch.setattr(lease.requests, "get", fake_get)
    return lease.LeaseClient(base_url="http://fleet:8096", secret="s3cr3t"), calls


def test_acquire_success(monkeypatch):
    lo = {"id": "abc", "holder": "h", "target": {"type": "node", "name": "node2"},
          "mode": "exclusive", "notes": "", "acquired": "t", "expires": "t2"}
    c, calls = make_client(monkeypatch, [(200, {"ok": True, "lease": lo})])
    got = c.acquire("h", "node", "node2", ttl_sec=28800, notes="train")
    assert got["id"] == "abc"
    assert calls[0]["url"] == "http://fleet:8096/leases/acquire"
    assert calls[0]["headers"]["Authorization"] == "Bearer s3cr3t"
    assert calls[0]["body"]["target"] == {"type": "node", "name": "node2"}
    assert calls[0]["body"]["ttl_sec"] == 28800


def test_acquire_refused_raises(monkeypatch):
    c, _ = make_client(monkeypatch, [(409, {"ok": False, "error": "already held by x"})])
    with pytest.raises(lease.LeaseRefused, match="already held"):
        c.acquire("h", "node", "node2")


def test_unreachable_raises(monkeypatch):
    def boom(*a, **k):
        raise requests.ConnectionError("no route")
    monkeypatch.setattr(lease.requests, "post", boom)
    c = lease.LeaseClient(base_url="http://fleet:8096", secret="s")
    with pytest.raises(lease.FleetUnreachable):
        c.renew("abc")


def test_server_error_maps_to_unreachable(monkeypatch):
    c, _ = make_client(monkeypatch, [(500, {"ok": False})])
    with pytest.raises(lease.FleetUnreachable):
        c.renew("abc")


def test_renew_request_shape(monkeypatch):
    c, calls = make_client(monkeypatch, [(200, {"ok": True, "lease": {"id": "abc", "expires": "t2"}})])
    c.renew("abc", ttl_sec=3600)
    assert calls[0]["url"] == "http://fleet:8096/leases/renew"
    assert calls[0]["body"] == {"id": "abc", "ttl_sec": 3600}
    assert calls[0]["headers"]["Authorization"] == "Bearer s3cr3t"


def test_floor_target_includes_min_floor(monkeypatch):
    lo = {"id": "f1", "target": {"type": "pool", "name": "deepseek-v4-flash", "min_floor": 1}}
    c, calls = make_client(monkeypatch, [(200, {"ok": True, "lease": lo})])
    c.acquire("h", "pool", "deepseek-v4-flash", mode="floor", min_floor=1)
    assert calls[0]["body"]["target"]["min_floor"] == 1
    assert calls[0]["body"]["mode"] == "floor"


def test_release_and_node(monkeypatch):
    fleet = {"nodes": [{"name": "node2", "serving": []}, {"name": "node-multi", "serving": [{"model": "m"}]}]}
    c, calls = make_client(monkeypatch, [(200, {"ok": True, "released": "abc", "existed": True}),
                                     (200, fleet), (200, fleet)])
    assert c.release("abc") is True
    assert c.node("node-multi")["serving"] == [{"model": "m"}]
    assert c.node("ghost") is None
    assert calls[0]["url"] == "http://fleet:8096/leases/release"
    assert calls[0]["body"] == {"id": "abc"}
    assert calls[1]["url"] == "http://fleet:8096/fleet.json"
