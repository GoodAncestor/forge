from pathlib import Path

import yaml

from forge import config, envs

METHODS = {"cpt-qlora", "sft-lora", "dpo", "grpo", "reap", "abliterate",
           "quantize-gguf", "quantize-awq", "quantize-nvfp4", "smoke"}
REQUIRED = {"name", "profile", "method", "model_path", "datasets",
            "command", "params", "grace_sec", "push_to_hf"}


class RecipeError(ValueError):
    pass


def load_recipe(path):
    r = yaml.safe_load(Path(path).read_text())
    if not isinstance(r, dict):
        raise RecipeError("recipe must be a YAML mapping")
    missing = REQUIRED - set(r)
    if missing:
        raise RecipeError(f"missing keys: {sorted(missing)}")
    if r["method"] not in METHODS:
        raise RecipeError(f"unknown method {r['method']!r}")
    if r["profile"] not in envs.load_profiles():
        raise RecipeError(f"unknown profile {r['profile']!r}")
    if not (isinstance(r["command"], list) and r["command"]
            and all(isinstance(c, str) for c in r["command"])):
        raise RecipeError("command must be a non-empty list of strings")
    if not isinstance(r["grace_sec"], int) or r["grace_sec"] <= 0:
        raise RecipeError("grace_sec must be a positive integer")
    return r


def render_command(recipe, run_dir, recipe_path):
    subs = {"recipe_path": str(recipe_path), "run_dir": str(run_dir),
            "model_root": config.MODEL_ROOT, "data_root": config.DATA_ROOT}
    return [c.format(**subs) for c in recipe["command"]]
