"""GGUF conversion + quantization entrypoint. Fast subprocess job (no SIGTERM
handling needed) but keeps the runner's exit-code contract: 0 completed,
3 failed. Uses llama.cpp's converter + quantizer, installed by bootstrap
(Task 13) at params.llama_cpp_dir — forge does not vendor llama.cpp."""
import argparse
import subprocess
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
    model_dir = Path(config.MODEL_ROOT) / recipe["model_path"]

    f16_out = run_dir / "model-f16.gguf"
    quant_out = run_dir / f"model-{p['quant']}.gguf"

    convert = [sys.executable, f"{p['llama_cpp_dir']}/convert_hf_to_gguf.py",
               str(model_dir), "--outfile", str(f16_out), "--outtype", "f16"]
    quant = [f"{p['llama_cpp_dir']}/build/bin/llama-quantize",
             str(f16_out), str(quant_out), p["quant"]]

    subprocess.run(convert, check=True)
    subprocess.run(quant, check=True)
    return common.EXIT_OK


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:  # any conversion/quant error → exit 3 for the runner
        print(f"FAILED: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(common.EXIT_JOB)
