import pytest
from forge import envs


def test_load_profiles_from_repo():
    profiles = envs.load_profiles(overlay={})
    assert set(profiles) == {"cuda-ada", "cuda-blackwell", "cuda-datacenter", "rocm"}
    assert profiles["cuda-ada"]["status"] == "locked"


def test_no_overlay_means_empty_fleet():
    # public clone with no private overlay: every profile resolves, no hosts
    profiles = envs.load_profiles(overlay={})
    assert profiles["cuda-ada"]["hosts"] == []
    assert profiles["cuda-ada"]["smoke_host"] is None


def test_overlay_binds_hosts():
    overlay = {"cuda-blackwell": {"hosts": ["node2", "node3"],
                                  "smoke_host": "node3"}}
    profiles = envs.load_profiles(overlay=overlay)
    assert profiles["cuda-blackwell"]["hosts"] == ["node2", "node3"]
    assert profiles["cuda-blackwell"]["smoke_host"] == "node3"
    assert envs.profile_for_host("node2", profiles) == "cuda-blackwell"
    assert envs.profile_for_host("nonexistent", profiles) is None


def test_overlay_loaded_from_file(tmp_path, monkeypatch):
    overlay_file = tmp_path / "profiles.hosts.yaml"
    overlay_file.write_text("cuda-ada: {hosts: [node5], smoke_host: node5}\n")
    monkeypatch.setenv(envs.OVERLAY_ENV, str(tmp_path))  # dir form
    profiles = envs.load_profiles()
    assert profiles["cuda-ada"]["hosts"] == ["node5"]


def test_invalid_status_rejected(tmp_path):
    bad = tmp_path / "p.yaml"
    bad.write_text("profiles:\n  x:\n    description: d\n    torch_index: i\n"
                   "    status: wat\n")
    with pytest.raises(envs.ProfileError):
        envs.load_profiles(bad, overlay={})


def test_env_list_cli(capsys, monkeypatch):
    import json
    from forge import cli
    monkeypatch.delenv(envs.OVERLAY_ENV, raising=False)
    rc = cli.main(["--json", "env", "list"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert "cuda-blackwell" in out["profiles"]
