"""Boundary eval for the Talkie demo. GPU node, profile env:
uv run --project envs/cuda-blackwell python scripts/eval_boundary.py \
    --model /mnt/models/talkie-lm/talkie-1930-13b-base --adapter RUN/adapter --json
Scoring: knows-pre-1980 -> expected string appears in the completion;
refuses-post-1980 / hallucination-bait -> expected string must NOT be a
confident answer; flagged for human/LLM review rather than auto-scored."""
import argparse
import json
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--adapter", default=None)
    ap.add_argument("--evals", default="evals/talkie-1980-boundary.jsonl")
    ap.add_argument("--max-tokens", type=int, default=80)
    ap.add_argument("--json", action="store_true", dest="as_json")
    args = ap.parse_args()

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tok = AutoTokenizer.from_pretrained(args.model)
    model = AutoModelForCausalLM.from_pretrained(
        args.model, torch_dtype=torch.bfloat16, device_map="auto")
    if args.adapter:
        from peft import PeftModel
        model = PeftModel.from_pretrained(model, args.adapter)

    results = []
    for line in Path(args.evals).read_text().splitlines():
        e = json.loads(line)
        ids = tok(e["prompt"], return_tensors="pt").to(model.device)
        out = model.generate(**ids, max_new_tokens=args.max_tokens,
                             do_sample=False, pad_token_id=tok.eos_token_id)
        text = tok.decode(out[0][ids["input_ids"].shape[1]:],
                          skip_special_tokens=True)
        hit = e["expect"].lower() in text.lower()
        passed = hit if e["category"] == "knows-pre-1980" else None
        results.append({**e, "completion": text.strip(), "auto_pass": passed})

    knows = [r for r in results if r["category"] == "knows-pre-1980"]
    payload = {
        "knows_pre_1980_pass_rate": sum(bool(r["auto_pass"]) for r in knows) / len(knows),
        "needs_review": [r for r in results if r["auto_pass"] is None],
        "results": results,
    }
    print(json.dumps(payload, indent=2) if args.as_json else
          f"knows-pre-1980: {payload['knows_pre_1980_pass_rate']:.0%}; "
          f"{len(payload['needs_review'])} completions need review")


if __name__ == "__main__":
    main()
