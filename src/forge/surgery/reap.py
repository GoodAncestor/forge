"""Wrapper around the REAP expert-pruning tool. The tool itself is
cloned/installed by bootstrap (Task 13). params.tool_cmd is the FULL argv
template, verified against the tool's --help at install time — forge does
not hardcode tool CLIs."""
import argparse
import subprocess
import sys

from forge import config
from forge.train import common


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--recipe", required=True)
    ap.add_argument("--run-dir", required=True)
    args = ap.parse_args(argv)
    recipe = common.read_recipe(args.recipe)
    tool_cmd = recipe["params"].get("tool_cmd")
    if not tool_cmd:
        print("params.tool_cmd is required: set the verified tool argv in the "
              "recipe (see recipe notes)", file=sys.stderr)
        return 2
    cmd = [c.format(model_root=config.MODEL_ROOT, run_dir=args.run_dir)
           for c in tool_cmd]
    result = subprocess.run(cmd)
    if result.returncode != 0:
        return common.EXIT_JOB
    return common.EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
