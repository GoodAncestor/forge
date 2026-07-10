"""SFT/LoRA entrypoint. GPU-only; run via forge run under a profile env.
Exit: 0 completed, 75 paused-by-signal (checkpointed), 3 failed."""
import argparse
import sys

from forge.train import common
from forge.train._sft_impl import run

DEFAULTS = {"lora_r": 16, "lora_alpha": 32}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--recipe", required=True)
    ap.add_argument("--run-dir", required=True)
    args = ap.parse_args(argv)

    recipe = common.read_recipe(args.recipe)
    return run(recipe, args.run_dir, DEFAULTS)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:  # any training error → exit 3 for the runner
        print(f"FAILED: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(common.EXIT_JOB)
