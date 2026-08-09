"""tool_cmd rendering for the surgery wrappers, and the abliterix recipe.

The `{model_path}` placeholder is what makes one abliteration recipe reusable
across models; without it every tool_cmd hardcodes a path and the recipe stops
being a template."""
import pytest
import yaml

from forge import recipes
from forge.train import common

REPO_RECIPE = "recipes/abliterate-abliterix.yaml"


def test_render_substitutes_run_dir_and_model_root():
    out = common.render_tool_cmd(
        ["t", "--out", "{run_dir}/x", "--root", "{model_root}"],
        {"model_path": "m"}, "/runs/1", "/mnt/models")
    assert out == ["t", "--out", "/runs/1/x", "--root", "/mnt/models"]


def test_relative_model_path_resolves_against_model_root(tmp_path):
    (tmp_path / "org" / "mdl").mkdir(parents=True)
    out = common.render_tool_cmd(["t", "--model", "{model_path}"],
                                 {"model_path": "org/mdl"}, "/runs/1",
                                 str(tmp_path))
    assert out[-1] == str(tmp_path / "org" / "mdl")


def test_hf_repo_id_passes_through_when_not_on_disk(tmp_path):
    """A repo id like `OpenYourMind/GLM-5.2-abliterated` is a legitimate value
    for most tools' --model; it must not be mangled into a bogus local path
    just because it contains a slash."""
    out = common.render_tool_cmd(["t", "--model", "{model_path}"],
                                 {"model_path": "OpenYourMind/GLM-5.2-abliterated"},
                                 "/runs/1", str(tmp_path))
    assert out[-1] == "OpenYourMind/GLM-5.2-abliterated"


def test_absolute_model_path_is_untouched(tmp_path):
    out = common.render_tool_cmd(["t", "{model_path}"],
                                 {"model_path": "/abs/model"}, "/r", str(tmp_path))
    assert out[-1] == "/abs/model"


def test_abliterix_recipe_is_valid_and_wired():
    r = recipes.load_recipe(REPO_RECIPE)
    assert r["method"] == "abliterate"
    assert r["params"]["tool_cmd"][0] == "abliterix"


def test_abliterix_recipe_tool_cmd_renders_without_stray_placeholders(tmp_path):
    r = yaml.safe_load(open(REPO_RECIPE).read())
    out = common.render_tool_cmd(r["params"]["tool_cmd"], r, "/runs/x",
                                 str(tmp_path))
    assert not any("{" in c for c in out), out
    assert "/runs/x/abliterated" in out


@pytest.mark.parametrize("module_name", ["forge.surgery.abliterate",
                                         "forge.surgery.reap"])
def test_null_tool_cmd_still_refuses(tmp_path, module_name):
    """The stock recipes keep tool_cmd null; adding {model_path} must not
    weaken the refusal-to-guess contract."""
    import importlib
    mod = importlib.import_module(module_name)
    p = tmp_path / "r.yaml"
    p.write_text("name: x\nprofile: cuda-blackwell\nmethod: abliterate\n"
                 "model_path: m\ndatasets: []\ncommand: ['x']\n"
                 "params:\n  tool_cmd: null\ngrace_sec: 600\npush_to_hf: false\n")
    assert mod.main(["--recipe", str(p), "--run-dir", str(tmp_path)]) == 2
