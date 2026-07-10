import json
from pathlib import Path

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
