import pytest

from forge import data


def test_load_repo_manifest():
    entries = data.load_manifest()
    names = [e["name"] for e in entries]
    assert "nemotron-cc" in names
    assert len(names) == len(set(names)), "duplicate names"
    assert all(e["approved"] is False for e in entries), "nothing pre-approved"


def test_bad_tier_rejected(tmp_path):
    p = tmp_path / "m.yaml"
    p.write_text("datasets:\n- name: x\n  source: hf://a/b\n  tier: nope\n"
                 "  license: l\n  approved: false\n  size_bytes: null\n  nas_path: x/\n")
    with pytest.raises(data.ManifestError, match="tier"):
        data.load_manifest(p)


def test_bad_nas_path_rejected(tmp_path):
    p = tmp_path / "m.yaml"
    p.write_text("datasets:\n- name: x\n  source: hf://a/b\n  tier: pretraining\n"
                 "  license: l\n  approved: false\n  size_bytes: null\n  nas_path: ../evil\n")
    with pytest.raises(data.ManifestError, match="nas_path"):
        data.load_manifest(p)


def test_bad_source_scheme_rejected(tmp_path):
    p = tmp_path / "m.yaml"
    p.write_text("datasets:\n- name: x\n  source: ftp://a/b\n  tier: pretraining\n"
                 "  license: l\n  approved: false\n  size_bytes: null\n  nas_path: x/\n")
    with pytest.raises(data.ManifestError, match="source"):
        data.load_manifest(p)


def test_usage_bytes(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "f").write_bytes(b"x" * 1000)
    assert data.usage_bytes(tmp_path) == 1000


def test_data_list_cli(capsys):
    import json
    from forge import cli
    rc = cli.main(["--json", "data", "list", "--tier", "sft-preference"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert all(e["tier"] == "sft-preference" for e in out["datasets"])


def test_save_manifest_preserves_header(tmp_path):
    p = tmp_path / "m.yaml"
    entries = [{"name": "x", "source": "hf://a/b", "tier": "pretraining",
                "license": "l", "approved": False, "size_bytes": None,
                "nas_path": "x/"}]
    data.save_manifest(entries, p)
    text = p.read_text()
    assert text.startswith("# forge dataset archive manifest.")
    assert "flipped ONLY by Colby" in text
    assert data.load_manifest(p)[0]["name"] == "x"
