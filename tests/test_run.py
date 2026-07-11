import json
import os
import subprocess
import sys

from forge import run as run_mod
from forge.lease import LeaseRefused


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


class RefusingClient(StubClient):
    def node(self, name):
        return {"name": name, "serving": []}

    def acquire(self, *a, **k):
        raise LeaseRefused("node already held exclusively")


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


# --- C1: profile envs (envs/<profile>) are separate uv projects that don't
# install the root `forge` package. _child_env must put src/ on PYTHONPATH
# so `uv run --project envs/<profile> python -m forge.train.*` can import
# forge at all. ---

def test_child_env_puts_repo_src_on_pythonpath(tmp_path):
    env = run_mod._child_env(tmp_path)
    assert env["FORGE_RUN_DIR"] == str(tmp_path)
    entries = env["PYTHONPATH"].split(os.pathsep)
    assert str(run_mod.REPO_ROOT / "src") in entries


def test_child_env_prepends_to_existing_pythonpath(tmp_path, monkeypatch):
    monkeypatch.setenv("PYTHONPATH", "/some/other/path")
    env = run_mod._child_env(tmp_path)
    assert env["PYTHONPATH"] == str(run_mod.REPO_ROOT / "src") + os.pathsep + "/some/other/path"


def test_child_env_pythonpath_delivers_forge_via_real_uv_project(tmp_path):
    """Exercises the REAL uv-project composition run.execute() uses (`uv run
    --project envs/<profile> ...`) against a tmp minimal uv project standing
    in for a real profile env — the real envs/<profile> projects are
    GPU/Linux-only and can't be uv-synced here. The tmp project has no forge
    dependency, matching every real profile env. Without the _child_env
    PYTHONPATH fix this genuinely fails (ModuleNotFoundError: forge) because
    the tmp project's own venv has no access to src/forge; with the fix it
    passes because PYTHONPATH is honored by the child interpreter regardless
    of which venv `uv run --project` activates."""
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "pyproject.toml").write_text(
        "[project]\n"
        'name = "t"\n'
        'version = "0"\n'
        'requires-python = ">=3.11"\n'
        "dependencies = []\n"
    )
    env = run_mod._child_env(tmp_path / "rundir")
    r = subprocess.run(
        ["uv", "run", "--project", str(proj), "python", "-c", "import forge; print(forge.__file__)"],
        cwd=str(run_mod.REPO_ROOT), env=env, capture_output=True, text=True,
    )
    assert r.returncode == 0, f"stdout={r.stdout!r} stderr={r.stderr!r}"
    assert "src/forge/__init__.py" in r.stdout.replace(os.sep, "/")


# --- I1: --profile overrides env selection only, not the recipe itself ---

def test_profile_override_composes_alt_env_cmd(tmp_path, capsys):
    p = _write(tmp_path, RECIPE)  # recipe profile is cuda-blackwell
    rc = run_mod.execute(recipe_path=p, host="anywhere", off_fleet=True,
                         run_root=tmp_path / "runs", as_json=True,
                         dry_run=True, profile="cuda-ada")
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert str(run_mod.REPO_ROOT / "envs" / "cuda-ada") in out["cmd"]
    assert str(run_mod.REPO_ROOT / "envs" / "cuda-blackwell") not in out["cmd"]


def test_profile_override_invalid_exits_2(tmp_path, capsys):
    p = _write(tmp_path, RECIPE)
    rc = run_mod.execute(recipe_path=p, host="anywhere", off_fleet=True,
                         run_root=tmp_path / "runs", as_json=True,
                         dry_run=True, profile="not-a-real-profile")
    assert rc == 2
    err = json.loads(capsys.readouterr().out)
    assert "not-a-real-profile" in err["error"]


# --- I2: --resume reuses an existing run dir instead of a fresh timestamped one ---

def test_resume_reuses_existing_run_dir_with_checkpoints(tmp_path):
    run_dir = tmp_path / "runs" / "prior-run"
    (run_dir / "checkpoints").mkdir(parents=True)
    p = _write(tmp_path, RECIPE)
    rc = run_mod.execute(recipe_path=p, host="anywhere", off_fleet=True,
                         as_json=True, use_uv_project=False, resume=run_dir)
    assert rc == 0
    manifest = json.loads((run_dir / "run.json").read_text())
    assert manifest["run_dir"] == str(run_dir)
    assert manifest["outcome"] == "completed"


def test_resume_nonexistent_dir_exits_2(tmp_path, capsys):
    p = _write(tmp_path, RECIPE)
    missing = tmp_path / "does-not-exist"
    rc = run_mod.execute(recipe_path=p, host="anywhere", off_fleet=True,
                         as_json=True, use_uv_project=False, resume=missing)
    assert rc == 2
    err = json.loads(capsys.readouterr().out)
    assert str(missing) in err["error"]


def test_resume_dir_without_markers_exits_2(tmp_path):
    run_dir = tmp_path / "runs" / "empty-run"
    run_dir.mkdir(parents=True)
    p = _write(tmp_path, RECIPE)
    rc = run_mod.execute(recipe_path=p, host="anywhere", off_fleet=True,
                         as_json=True, use_uv_project=False, resume=run_dir)
    assert rc == 2


# --- Minor: run_dir is only created after a fleet lease is actually
# acquired (no empty dir left behind on the refusal path), and dry-run
# never creates one at all. ---

def test_refused_lease_does_not_create_run_dir(tmp_path, monkeypatch):
    client = RefusingClient()
    monkeypatch.setattr(run_mod, "LeaseClient", lambda *a, **k: client)
    p = _write(tmp_path, RECIPE)
    rc = run_mod.execute(recipe_path=p, host="alien02", off_fleet=False,
                         run_root=tmp_path / "runs", as_json=True,
                         use_uv_project=False)
    assert rc == 2
    assert not (tmp_path / "runs").exists()


def test_dry_run_does_not_create_run_dir(tmp_path):
    p = _write(tmp_path, RECIPE)
    rc = run_mod.execute(recipe_path=p, host="anywhere", off_fleet=True,
                         run_root=tmp_path / "runs", as_json=True,
                         dry_run=True)
    assert rc == 0
    assert not (tmp_path / "runs").exists()


def test_mkdir_failure_still_releases_lease(tmp_path, monkeypatch):
    client = StubClient()
    monkeypatch.setattr(run_mod, "LeaseClient", lambda *a, **k: client)
    p = _write(tmp_path, RECIPE)
    blocker = tmp_path / "runs"
    blocker.write_text("not a directory")
    rc = run_mod.execute(recipe_path=p, host="alien02", off_fleet=False,
                         run_root=blocker, as_json=True,
                         use_uv_project=False, poll_sec=0.1)
    assert rc == 3
    assert client.released == ["L1"]


# --- Task 5: run lifecycle + heartbeat posts to the /forge status panel ---

def _capture_posts(monkeypatch):
    posts = []
    from forge import status
    monkeypatch.setattr(status, "post",
                        lambda kind, id, state, payload=None:
                        posts.append((kind, id, state, payload)) or True)
    return posts


def test_run_posts_running_then_completed(tmp_path, monkeypatch):
    posts = _capture_posts(monkeypatch)
    p = _write(tmp_path, RECIPE)
    rc = run_mod.execute(recipe_path=p, host="testhost", off_fleet=True,
                         run_root=tmp_path / "runs", as_json=True,
                         use_uv_project=False)
    assert rc == 0
    states = [s for k, _, s, _ in posts if k == "run"]
    assert states[0] == "running" and states[-1] == "completed"
    term = posts[-1][3]
    assert term["exit_code"] == 0 and term["host"] == "testhost"
    assert "run_dir" in term and term["recipe"] == "t"


def test_run_posts_paused_on_checkpoint_exit(tmp_path, monkeypatch):
    # Mirrors test_heartbeat_lost_pauses_job: off_fleet=True runs never
    # construct a heartbeat, so pausing via InstantLostHB needs the
    # off_fleet=False path with a fake lease client.
    posts = _capture_posts(monkeypatch)
    client = StubClient()
    monkeypatch.setattr(run_mod, "LeaseClient", lambda *a, **k: client)
    monkeypatch.setattr(run_mod, "LeaseHeartbeat", InstantLostHB)
    p = _write(tmp_path, SLEEPER)
    rc = run_mod.execute(recipe_path=p, host="alien02", off_fleet=False,
                         run_root=tmp_path / "runs", as_json=True,
                         use_uv_project=False, poll_sec=0.1)
    assert rc == 75
    states = [s for k, _, s, _ in posts if k == "run"]
    assert states[-1] == "paused"


def test_latest_checkpoint_parses_max(tmp_path):
    ck = tmp_path / "checkpoints"
    ck.mkdir()
    for n in (3, 10, 7):
        (ck / f"checkpoint-{n}").mkdir()
    (ck / "checkpoint-junk").mkdir()
    assert run_mod._latest_checkpoint(tmp_path) == 10
    assert run_mod._latest_checkpoint(tmp_path / "nope") is None
