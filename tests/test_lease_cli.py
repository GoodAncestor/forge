import json

from forge import cli, lease_cli
from forge.lease import LeaseRefused, FleetUnreachable


class StubClient:
    def __init__(self, *a, **k):
        pass

    def acquire(self, holder, target_type, name, mode="exclusive",
                ttl_sec=28800, notes="", min_floor=None):
        if name == "held":
            raise LeaseRefused("node held is already held exclusively by other")
        return {"id": "L1", "holder": holder, "mode": mode,
                "target": {"type": target_type, "name": name}, "expires": "t"}

    def renew(self, lease_id, ttl_sec=28800):
        return {"id": lease_id, "expires": "t2"}

    def release(self, lease_id):
        return True

    def fleet(self):
        return {"nodes": [{"name": "node2", "held_by": "someone",
                           "serving": []}]}


class DownClient(StubClient):
    def acquire(self, *a, **k):
        raise FleetUnreachable("no route")


def test_acquire_ok(monkeypatch, capsys):
    monkeypatch.setattr(lease_cli, "LeaseClient", StubClient)
    rc = cli.main(["--json", "lease", "acquire", "--target-type", "node",
                   "--name", "node2"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["lease"]["id"] == "L1"


def test_acquire_refused_exit_2(monkeypatch, capsys):
    monkeypatch.setattr(lease_cli, "LeaseClient", StubClient)
    rc = cli.main(["--json", "lease", "acquire", "--target-type", "node",
                   "--name", "held"])
    assert rc == 2
    assert "already held" in json.loads(capsys.readouterr().out)["error"]


def test_unreachable_exit_4(monkeypatch, capsys):
    monkeypatch.setattr(lease_cli, "LeaseClient", DownClient)
    rc = cli.main(["--json", "lease", "acquire", "--target-type", "node",
                   "--name", "node2"])
    assert rc == 4


def test_status(monkeypatch, capsys):
    monkeypatch.setattr(lease_cli, "LeaseClient", StubClient)
    rc = cli.main(["--json", "lease", "status"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["nodes"][0]["held_by"] == "someone"


class NullServingClient(StubClient):
    def fleet(self):
        return {"nodes": [{"name": "node2", "held_by": None, "serving": None}]}


def test_status_guards_null_serving(monkeypatch, capsys):
    monkeypatch.setattr(lease_cli, "LeaseClient", NullServingClient)
    rc = cli.main(["--json", "lease", "status"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["nodes"][0]["serving"] == []
