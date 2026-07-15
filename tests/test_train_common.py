import signal

import pytest

from forge.train import common

SURGERY_RECIPE = """\
name: x
profile: cuda-blackwell
method: {method}
model_path: m
datasets: []
command: ['x']
params:
  tool_cmd: null
grace_sec: 600
push_to_hf: false
"""


def test_stopflag_sets_on_sigterm():
    flag = common.StopFlag()
    flag.install()
    signal.raise_signal(signal.SIGTERM)
    assert flag.triggered


def test_checkpoint_dir_resolution(tmp_path):
    ck = tmp_path / "checkpoints"
    assert common.latest_checkpoint(ck) is None
    (ck / "checkpoint-100").mkdir(parents=True)
    (ck / "checkpoint-250").mkdir()
    (ck / "not-a-checkpoint").mkdir()
    assert common.latest_checkpoint(ck).name == "checkpoint-250"


def test_load_recipe_params(tmp_path):
    p = tmp_path / "r.yaml"
    p.write_text("name: x\nprofile: cuda-blackwell\nmethod: sft-lora\n"
                 "model_path: m\ndatasets: []\ncommand: ['x']\n"
                 "params:\n  lora_r: 64\ngrace_sec: 600\npush_to_hf: false\n")
    r = common.read_recipe(p)
    assert r["params"]["lora_r"] == 64


def test_entrypoints_import_without_gpu():
    """All train/quant/surgery entrypoints must import cleanly without torch —
    GPU libraries are imported lazily inside main()/run(), never at module
    scope. This is what lets `forge run` compile these under CI and lets the
    runner select an entrypoint without a GPU env present."""
    import forge.quant.compress
    import forge.quant.gguf
    import forge.surgery.abliterate
    import forge.surgery.reap
    import forge.train.cpt
    import forge.train.dpo
    import forge.train.grpo
    import forge.train.sft

    for mod in (forge.train.sft, forge.train.cpt, forge.train.dpo, forge.train.grpo,
                forge.quant.gguf, forge.quant.compress, forge.surgery.reap,
                forge.surgery.abliterate):
        assert hasattr(mod, "main")


@pytest.mark.parametrize("module_name, method", [
    ("forge.surgery.reap", "reap"),
    ("forge.surgery.abliterate", "abliterate"),
])
def test_surgery_wrapper_requires_tool_cmd(tmp_path, module_name, method):
    """params.tool_cmd is null until an operator verifies the external tool's
    --help and fills it in (Task 13 bootstrap); the wrapper must refuse to
    guess a CLI and exit 2 — no subprocess ever gets spawned."""
    import importlib
    mod = importlib.import_module(module_name)

    recipe_path = tmp_path / "r.yaml"
    recipe_path.write_text(SURGERY_RECIPE.format(method=method))
    run_dir = tmp_path / "run"

    rc = mod.main(["--recipe", str(recipe_path), "--run-dir", str(run_dir)])
    assert rc == 2
