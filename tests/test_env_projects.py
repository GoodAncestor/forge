from pathlib import Path

from forge import envs

REPO = Path(__file__).resolve().parents[1]


def test_every_nonstub_profile_has_project_and_lock():
    for name, p in envs.load_profiles().items():
        d = REPO / "envs" / name
        if p["status"] == "stub":
            assert (d / "PACKAGES.md").exists(), f"{name}: stub needs PACKAGES.md"
        else:
            assert (d / "pyproject.toml").exists(), f"{name}: missing pyproject"
            assert (d / "uv.lock").exists(), f"{name}: missing uv.lock"


def test_smoke_script_exists_and_compiles():
    src = (REPO / "envs" / "smoke.py").read_text()
    compile(src, "smoke.py", "exec")
