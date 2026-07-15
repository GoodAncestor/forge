"""Smoke test for a forge env profile. Run on a GPU node, under lease:
    uv run --project envs/<profile> python envs/smoke.py --gpu
Without --gpu it only checks imports (usable in CI containers).
Prints one JSON object; exit 0 = all pass, 3 = any failure.
"""
import argparse
import importlib
import json
import sys

CORE = ["torch", "transformers", "datasets", "accelerate", "peft", "trl"]
EXTRA = ["bitsandbytes", "unsloth", "deepspeed", "llmcompressor", "gptqmodel", "lm_eval"]


def try_import(mod):
    try:
        m = importlib.import_module(mod)
        return {"ok": True, "version": getattr(m, "__version__", None)}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def gpu_checks():
    import torch
    out = {"cuda_available": torch.cuda.is_available()}
    if not out["cuda_available"]:
        return out
    out["device_name"] = torch.cuda.get_device_name(0)
    out["capability"] = ".".join(map(str, torch.cuda.get_device_capability(0)))
    a = torch.randn(1024, 1024, device="cuda", dtype=torch.bfloat16)
    out["bf16_matmul_ok"] = bool(((a @ a).sum()).isfinite().item())
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gpu", action="store_true")
    args = ap.parse_args()
    report = {"imports": {m: try_import(m) for m in CORE + EXTRA}}
    if args.gpu:
        try:
            report["gpu"] = gpu_checks()
        except Exception as e:
            report["gpu"] = {"error": str(e)}
    core_ok = all(report["imports"][m]["ok"] for m in CORE)
    gpu_ok = (not args.gpu) or report.get("gpu", {}).get("bf16_matmul_ok", False)
    report["ok"] = bool(core_ok and gpu_ok)
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 3


if __name__ == "__main__":
    sys.exit(main())
