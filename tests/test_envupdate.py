import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

from forge import envupdate

LOCK_BEFORE = """\
version = 1
[[package]]
name = "torch"
version = "2.9.0"
[[package]]
name = "trl"
version = "0.19.0"
"""

LOCK_AFTER = """\
version = 1
[[package]]
name = "torch"
version = "2.10.0"
[[package]]
name = "trl"
version = "0.19.0"
[[package]]
name = "newpkg"
version = "1.0"
"""


def test_lock_versions(tmp_path):
    p = tmp_path / "uv.lock"
    p.write_text(LOCK_BEFORE)
    assert envupdate.lock_versions(p) == {"torch": "2.9.0", "trl": "0.19.0"}


def test_diff_versions():
    before = {"torch": "2.9.0", "trl": "0.19.0", "gone": "1"}
    after = {"torch": "2.10.0", "trl": "0.19.0", "newpkg": "1.0"}
    d = envupdate.diff_versions(before, after)
    assert d == {"changed": {"torch": ["2.9.0", "2.10.0"]},
                 "added": {"newpkg": "1.0"}, "removed": {"gone": "1"}}


def test_update_profile_runs_uv(tmp_path, monkeypatch):
    prof = tmp_path / "cuda-x"
    prof.mkdir()
    lock = prof / "uv.lock"
    lock.write_text(LOCK_BEFORE)
    calls = []

    def fake_run(cmd, cwd=None, check=False, capture_output=True, text=True):
        calls.append((cmd, cwd))
        lock.write_text(LOCK_AFTER)
        class R:
            returncode = 0
            stdout = stderr = ""
        return R()

    monkeypatch.setattr(envupdate.subprocess, "run", fake_run)
    diff = envupdate.update_profile(prof)
    assert calls[0][0] == ["uv", "lock", "--upgrade"]
    assert diff["changed"]["torch"] == ["2.9.0", "2.10.0"]


def test_report_written(tmp_path):
    report = envupdate.write_report(
        {"cuda-x": {"changed": {}, "added": {}, "removed": {}}},
        {"cuda-x": {"outcome": "skipped"}}, tmp_path)
    data = json.loads(Path(report).read_text())
    assert data["ok"] is True
    assert "cuda-x" in data["diffs"]


PR_URL = "https://github.com/example/forge/pull/42"


class FakeResult:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _make_fake_repo(tmp_path):
    profile_dir = tmp_path / "repo" / "envs" / "cuda-x"
    profile_dir.mkdir(parents=True)
    (profile_dir / "uv.lock").write_text(LOCK_BEFORE)
    return tmp_path / "repo"


def _fake_profiles():
    return {"cuda-x": {"description": "x", "torch_index": "x", "hosts": ["h1"],
                       "smoke_host": "h1", "status": "locked"}}


def _make_args(tmp_path):
    return SimpleNamespace(as_json=True, no_smoke=False, no_pr=False,
                           report_dir=str(tmp_path / "reports"))


def test_cmd_update_pr_path(tmp_path, monkeypatch, capsys):
    repo_root = _make_fake_repo(tmp_path)
    calls = []

    def fake_run(cmd, cwd=None, check=False, capture_output=False, text=False):
        calls.append(list(cmd))
        if cmd[:3] == ["uv", "lock", "--upgrade"]:
            (Path(cwd) / "uv.lock").write_text(LOCK_AFTER)
            return FakeResult(0)
        if cmd[:2] == ["uv", "run"]:
            return FakeResult(0)
        if cmd[:1] == ["gh"]:
            return FakeResult(0, stdout=PR_URL + "\n")
        return FakeResult(0)

    monkeypatch.setattr(envupdate.subprocess, "run", fake_run)
    monkeypatch.setattr(envupdate, "REPO_ROOT", repo_root)
    monkeypatch.setattr(envupdate.envs, "load_profiles", _fake_profiles)

    rc = envupdate.cmd_update(_make_args(tmp_path))

    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["pr"] == PR_URL
    assert "pr_error" not in payload

    report_data = json.loads(Path(payload["report"]).read_text())
    assert report_data["ok"] is True

    add_calls = [c for c in calls if c[:2] == ["git", "add"]]
    assert add_calls == [["git", "add", "envs/cuda-x/uv.lock"]]
    assert calls[-1] == ["git", "checkout", "main"]


def test_cmd_update_pr_failure_recovers_branch(tmp_path, monkeypatch, capsys):
    repo_root = _make_fake_repo(tmp_path)
    calls = []

    def fake_run(cmd, cwd=None, check=False, capture_output=False, text=False):
        calls.append(list(cmd))
        if cmd[:3] == ["uv", "lock", "--upgrade"]:
            (Path(cwd) / "uv.lock").write_text(LOCK_AFTER)
            return FakeResult(0)
        if cmd[:2] == ["uv", "run"]:
            return FakeResult(0)
        if cmd[:1] == ["gh"]:
            raise subprocess.CalledProcessError(1, cmd, output="", stderr="boom")
        return FakeResult(0)

    monkeypatch.setattr(envupdate.subprocess, "run", fake_run)
    monkeypatch.setattr(envupdate, "REPO_ROOT", repo_root)
    monkeypatch.setattr(envupdate.envs, "load_profiles", _fake_profiles)

    rc = envupdate.cmd_update(_make_args(tmp_path))

    assert rc == 3
    assert calls[-1] == ["git", "checkout", "main"]
