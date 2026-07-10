"""llmcompressor oneshot quantization entrypoint. Fast job — no SIGTERM
handling needed — but keeps the runner's exit-code contract: 0 completed,
3 failed.

params.scheme is passed straight through to QuantizationModifier as a
compressed-tensors preset scheme name (e.g. "NVFP4", "W4A16") so that a
locked-version preset rename/removal is a recipe edit, not a forge code
change — same philosophy as the surgery tool_cmd wrappers. See the task-12
report for a verified-against-locked-versions note on scheme naming (AWQ in
particular is an activation-aware *algorithm*, not itself a preset scheme
name, and needs calibration data via params.dataset_path)."""
import argparse
import sys
from pathlib import Path

from forge import config
from forge.train import common


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--recipe", required=True)
    ap.add_argument("--run-dir", required=True)
    args = ap.parse_args(argv)

    recipe = common.read_recipe(args.recipe)
    p = recipe["params"]
    run_dir = Path(args.run_dir)
    model_path = str(Path(config.MODEL_ROOT) / recipe["model_path"])
    out_dir = run_dir / "quantized"

    from llmcompressor import oneshot
    from llmcompressor.modifiers.quantization import QuantizationModifier

    recipe_mod = QuantizationModifier(scheme=p["scheme"], targets="Linear",
                                      ignore=list(p.get("ignore", ["lm_head"])))
    oneshot(
        model=model_path,
        recipe=recipe_mod,
        dataset=p.get("dataset_path"),
        num_calibration_samples=p.get("num_calibration_samples", 512),
        max_seq_length=p.get("max_seq_length", 2048),
        output_dir=str(out_dir),
    )
    return common.EXIT_OK


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:  # any quantization error → exit 3 for the runner
        print(f"FAILED: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(common.EXIT_JOB)
