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

IGNORER = """\
name: t
profile: cuda-blackwell
method: smoke
model_path: null
datasets: []
command: ["{python}", "-c", "import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(60)"]
params: {{}}
grace_sec: 1
push_to_hf: false
"""


class InstantLostHB:
    """Fires .lost shortly (not literally instantly) after construction —
    long enough for a just-spawned child process to finish interpreter
    startup and install its own signal handler before the runner's poll
    loop notices and sends SIGTERM. Without this delay the parent can win
    the race and SIGTERM the child before its handler is installed, which
    would make paused-vs-failed tests flaky/wrong regardless of run.py's
    own correctness."""

    def __init__(self, *a, **k):
        import threading
        self.lost = threading.Event()
        self._timer = threading.Timer(0.3, self.lost.set)
        self._timer.daemon = True
        self._timer.start()

    def start(self):
        pass

    def stop(self):
        self._timer.cancel()


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
    monkeypatch.setattr(run_mod, "LeaseHeartbeat", InstantLostHB)
    p = _write(tmp_path, SLEEPER)
    rc = run_mod.execute(recipe_path=p, host="alien02", off_fleet=False,
                         run_root=tmp_path / "runs", as_json=True,
                         use_uv_project=False, poll_sec=0.1)
    assert rc == 75
    manifest = json.loads(next((tmp_path / "runs").rglob("run.json")).read_text())
    assert manifest["outcome"] == "paused"
    assert client.released == ["L1"]


def test_launch_failure_releases_lease_and_writes_manifest(tmp_path, monkeypatch):
    client = StubClient()
    monkeypatch.setattr(run_mod, "LeaseClient", lambda *a, **k: client)
    p = _write(tmp_path, RECIPE.replace("{python}", "/nonexistent/binary-xyz"))
    rc = run_mod.execute(recipe_path=p, host="alien02", off_fleet=False,
                         run_root=tmp_path / "runs", as_json=True,
                         use_uv_project=False, poll_sec=0.1)
    assert rc == 3
    assert client.released == ["L1"]
    manifest = json.loads(next((tmp_path / "runs").rglob("run.json")).read_text())
    assert manifest["outcome"] == "failed"


def test_sigkilled_child_reports_failed_not_paused(tmp_path, monkeypatch):
    client = StubClient()
    monkeypatch.setattr(run_mod, "LeaseClient", lambda *a, **k: client)
    monkeypatch.setattr(run_mod, "LeaseHeartbeat", InstantLostHB)
    p = _write(tmp_path, IGNORER)
    rc = run_mod.execute(recipe_path=p, host="alien02", off_fleet=False,
                         run_root=tmp_path / "runs", as_json=True,
                         use_uv_project=False, poll_sec=0.1)
    assert rc == 3
    manifest = json.loads(next((tmp_path / "runs").rglob("run.json")).read_text())
    assert manifest["outcome"] == "failed"
    assert manifest["child_exit"] not in (0, 75)
