from forge import data


def _entry(name, approved=True, size=1000):
    return {"name": name, "source": f"hf://org/{name}", "tier": "pretraining",
            "license": "l", "approved": approved, "size_bytes": size,
            "nas_path": f"{name}/"}


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
