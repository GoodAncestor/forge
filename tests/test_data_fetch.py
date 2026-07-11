import yaml

from forge import data


def _entry(name, approved=True, size=1000):
    return {"name": name, "source": f"hf://org/{name}", "tier": "pretraining",
            "license": "l", "approved": approved, "size_bytes": size,
            "nas_path": f"{name}/"}


def _manifest(tmp_path, entries):
    """Write a manifest.yaml under tmp_path and return its path."""
    path = tmp_path / "manifest.yaml"
    path.write_text(yaml.safe_dump({"datasets": entries}, sort_keys=False))
    return path


class _Args:
    """Minimal argparse.Namespace stand-in for cmd_fetch."""

    def __init__(self, **kw):
        self.__dict__.update(kw)


def _args(**overrides):
    defaults = dict(name=None, tier=None, root=None, rate_limit=None,
                     dry_run=False, allow_unsized=False, as_json=True)
    defaults.update(overrides)
    return _Args(**defaults)


def _run_fetch_for_single_entry(tmp_path, monkeypatch, name="dataset-one"):
    """Build a manifest with one approved, sized entry and invoke cmd_fetch
    against it, returning cmd_fetch's return code."""
    entry = _entry(name)
    manifest_path = _manifest(tmp_path, [entry])
    monkeypatch.setattr(data, "MANIFEST_PATH", manifest_path)
    root = tmp_path / "root"
    root.mkdir()
    args = _args(name=name, root=str(root))
    return data.cmd_fetch(args)


def test_plan_refuses_unapproved(tmp_path):
    plan = data.plan_fetch([_entry("a", approved=False)], tmp_path, cap_bytes=10**9)
    assert plan["refused"][0]["reason"] == "not approved"
    assert plan["to_fetch"] == []


def test_plan_refuses_over_cap(tmp_path):
    big = _entry("big", size=2 * 10**9)
    plan = data.plan_fetch([big], tmp_path, cap_bytes=10**9)
    assert "cap" in plan["refused"][0]["reason"]


def test_plan_skips_already_fetched(tmp_path):
    e = _entry("done")
    d = tmp_path / "done"
    d.mkdir()
    (d / ".forge-complete").write_text("{}")
    plan = data.plan_fetch([e], tmp_path, cap_bytes=10**9)
    assert plan["skipped"][0]["name"] == "done"


def test_plan_counts_existing_usage_against_cap(tmp_path):
    (tmp_path / "old").mkdir()
    (tmp_path / "old" / "blob").write_bytes(b"x" * 600)
    plan = data.plan_fetch([_entry("a", size=500)], tmp_path, cap_bytes=1000)
    assert "cap" in plan["refused"][0]["reason"]


def test_plan_unknown_size_requires_flag(tmp_path):
    e = _entry("mystery", size=None)
    plan = data.plan_fetch([e], tmp_path, cap_bytes=10**9)
    assert plan["refused"][0]["reason"] == "size unknown (run `forge data sizes`, or pass --allow-unsized)"
    plan2 = data.plan_fetch([e], tmp_path, cap_bytes=10**9, allow_unsized=True)
    assert plan2["to_fetch"][0]["name"] == "mystery"


def test_fetch_requires_name_xor_tier(capsys):
    import json
    from forge import cli
    rc = cli.main(["--json", "data", "fetch"])
    assert rc == 2
    assert "exactly one" in json.loads(capsys.readouterr().out)["error"]
    rc = cli.main(["--json", "data", "fetch", "nemotron-cc", "--tier", "pretraining"])
    assert rc == 2


def test_plan_unsized_still_needs_headroom(tmp_path):
    (tmp_path / "old").mkdir()
    (tmp_path / "old" / "blob").write_bytes(b"x" * 1000)
    e = _entry("mystery", size=None)
    plan = data.plan_fetch([e], tmp_path, cap_bytes=1000, allow_unsized=True)
    assert "cap" in plan["refused"][0]["reason"]


def test_fetch_posts_lifecycle_states(tmp_path, monkeypatch):
    posts = []
    from forge import data as data_mod, status
    monkeypatch.setattr(status, "post",
                        lambda kind, id, state, payload=None:
                        posts.append((kind, id, state, payload)) or True)
    monkeypatch.setattr(data_mod, "fetch_entry",
                        lambda e, root, rate_limit=None: None)   # instant success
    # one approved, sized entry via the file's existing manifest fixture
    rc = _run_fetch_for_single_entry(tmp_path, monkeypatch)
    assert rc == 0
    states = [(k, i, s) for k, i, s, _ in posts]
    assert states[0][2] == "fetching" and states[-1][2] == "done"
    assert all(k == "fetch" for k, _, _ in states)
    done_payload = posts[-1][3]
    assert set(done_payload) >= {"bytes", "size_bytes", "nas_path", "tier"}


def test_fetch_failure_posts_error_state(tmp_path, monkeypatch):
    posts = []
    from forge import data as data_mod, status
    monkeypatch.setattr(status, "post",
                        lambda kind, id, state, payload=None:
                        posts.append((kind, id, state, payload)) or True)
    def boom(e, root, rate_limit=None):
        raise RuntimeError("disk full")
    monkeypatch.setattr(data_mod, "fetch_entry", boom)
    rc = _run_fetch_for_single_entry(tmp_path, monkeypatch)
    assert rc == 3
    assert posts[-1][2] == "error"
    assert "disk full" in posts[-1][3]["error"]


def test_status_payload_failure_never_breaks_fetch(tmp_path, monkeypatch):
    """Status post payload construction (which walks live NFS trees) must
    never break or mask a fetch outcome. _fetch_payload can raise during the
    walk; status posts must be guarded."""
    from forge import data as data_mod
    monkeypatch.setattr(data_mod, "fetch_entry",
                        lambda e, root, rate_limit=None: None)  # instant success
    def boom(entry, root):
        raise OSError("stale NFS handle")
    monkeypatch.setattr(data_mod, "_fetch_payload", boom)
    rc = _run_fetch_for_single_entry(tmp_path, monkeypatch)
    assert rc == 0  # fetch outcome unaffected by status layer blowing up
