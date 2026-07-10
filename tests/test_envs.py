import pytest
from forge import envs


def test_load_profiles_from_repo():
    profiles = envs.load_profiles()
    assert set(profiles) == {"cuda-ada", "cuda-blackwell", "cuda-datacenter", "rocm"}
    assert profiles["cuda-ada"]["status"] == "locked"


def test_profile_for_host():
    profiles = envs.load_profiles()
    assert envs.profile_for_host("alien02", profiles) == "cuda-blackwell"
    assert envs.profile_for_host("ai-silo", profiles) == "cuda-blackwell"
    assert envs.profile_for_host("nonexistent", profiles) is None


def test_invalid_status_rejected(tmp_path):
    bad = tmp_path / "p.yaml"
    bad.write_text("profiles:\n  x:\n    description: d\n    torch_index: i\n"
                   "    hosts: []\n    smoke_host: null\n    status: wat\n")
    with pytest.raises(envs.ProfileError):
        envs.load_profiles(bad)


def test_env_list_cli(capsys):
    import json
    from forge import cli
    rc = cli.main(["--json", "env", "list"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert "cuda-blackwell" in out["profiles"]
