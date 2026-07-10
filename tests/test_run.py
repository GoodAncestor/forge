import json
import sys

from forge import run as run_mod


RECIPE = """\
name: t
profile: cuda-blackwell
method: smoke
model_path: null
datasets: []
command: ["{python}", "-c", "print('hi')"]
params: {{}}
grace_sec: 2
push_to_hf: false
"""

SLEEPER = """\
name: t
profile: cuda-blackwell
method: smoke
model_path: null
datasets: []
command: ["{python}", "-c", "import signal,sys,time; signal.signal(signal.SIGTERM, lambda *a: sys.exit(75)); time.sleep(60)"]
params: {{}}
grace_sec: 2
push_to_hf: false
"""


def _write(tmp_path, text):
    p = tmp_path / "r.yaml"
    p.write_text(text.format(python=sys.executable))
    return p


class StubClient:
    def __init__(self, *a, **k):
        self.released = []

    def acquire(self, *a, **k):
        return {"id": "L1", "expires": "t"}

    def renew(self, lease_id, ttl_sec=28800):
        return {"id": lease_id}

    def release(self, lease_id):
        self.released.append(lease_id)
        return True

    def node(self, name):
        return {"name": name, "serving": [{"model": "prod-model", "port": 8000}]}


def test_off_fleet_success(tmp_path, capsys):
    p = _write(tmp_path, RECIPE)
    rc = run_mod.execute(recipe_path=p, host="anywhere", off_fleet=True,
                         run_root=tmp_path / "runs", as_json=True,
                         use_uv_project=False)
    assert rc == 0
    manifest = json.loads(next((tmp_path / "runs").rglob("run.json")).read_text())
    assert manifest["outcome"] == "completed"
    assert manifest["lease_id"] is None


def test_fleet_requires_lease_and_releases(tmp_path, monkeypatch):
    client = StubClient()
    monkeypatch.setattr(run_mod, "LeaseClient", lambda *a, **k: client)
    p = _write(tmp_path, RECIPE)
    rc = run_mod.execute(recipe_path=p, host="alien02", off_fleet=False,
                         run_root=tmp_path / "runs", as_json=True,
                         use_uv_project=False)
    assert rc == 0
    assert client.released == ["L1"]


def test_serving_node_warns(tmp_path, monkeypatch, capsys):
    client = StubClient()
    monkeypatch.setattr(run_mod, "LeaseClient", lambda *a, **k: client)
    p = _write(tmp_path, RECIPE)
    run_mod.execute(recipe_path=p, host="ai-silo", off_fleet=False,
                    run_root=tmp_path / "runs", as_json=False,
                    use_uv_project=False)
    err = capsys.readouterr().err
    assert "prod-model" in err and "floor" in err


def test_heartbeat_lost_pauses_job(tmp_path, monkeypatch):
    client = StubClient()
    monkeypatch.setattr(run_mod, "LeaseClient", lambda *a, **k: client)

    class InstantLostHB:
        def __init__(self, *a, **k):
            import threading
            self.lost = threading.Event()
            self.lost.set()

        def start(self):
            pass

        def stop(self):
            pass

    monkeypatch.setattr(run_mod, "LeaseHeartbeat", InstantLostHB)
    p = _write(tmp_path, SLEEPER)
    rc = run_mod.execute(recipe_path=p, host="alien02", off_fleet=False,
                         run_root=tmp_path / "runs", as_json=True,
                         use_uv_project=False, poll_sec=0.1)
    assert rc == 75
    manifest = json.loads(next((tmp_path / "runs").rglob("run.json")).read_text())
    assert manifest["outcome"] == "paused"
    assert client.released == ["L1"]
