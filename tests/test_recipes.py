import pytest

from forge import recipes

GOOD = """\
name: test-sft
profile: cuda-blackwell
method: sft-lora
model_path: talkie-lm/talkie-1930-13b-base
datasets: []
command: ["python", "-m", "forge.train.sft", "--recipe", "{recipe_path}", "--run-dir", "{run_dir}"]
params:
  lora_r: 16
grace_sec: 600
push_to_hf: false
"""


def test_load_good(tmp_path):
    p = tmp_path / "r.yaml"
    p.write_text(GOOD)
    r = recipes.load_recipe(p)
    assert r["name"] == "test-sft"
    assert r["grace_sec"] == 600


def test_unknown_profile_rejected(tmp_path):
    p = tmp_path / "r.yaml"
    p.write_text(GOOD.replace("cuda-blackwell", "cuda-nonexistent"))
    with pytest.raises(recipes.RecipeError, match="profile"):
        recipes.load_recipe(p)


def test_unknown_method_rejected(tmp_path):
    p = tmp_path / "r.yaml"
    p.write_text(GOOD.replace("sft-lora", "mystery-method"))
    with pytest.raises(recipes.RecipeError, match="method"):
        recipes.load_recipe(p)


def test_render_command(tmp_path):
    p = tmp_path / "r.yaml"
    p.write_text(GOOD)
    r = recipes.load_recipe(p)
    cmd = recipes.render_command(r, run_dir=tmp_path / "run", recipe_path=p)
    assert cmd[0] == "python"
    assert str(tmp_path / "run") in cmd
    assert str(p) in cmd


def test_all_shipped_recipes_valid():
    from pathlib import Path
    repo = Path(recipes.__file__).resolve().parents[2]
    files = sorted((repo / "recipes").glob("*.yaml"))
    assert len(files) >= 9
    for f in files:
        recipes.load_recipe(f)  # must not raise
