"""GRPO/LoRA entrypoint. GPU-only; run via forge run under a profile env.
Dataset must have a "prompt" column. Requires params.reward_module: a dotted
Python path under the repo root (e.g. "rewards.length_penalty") resolving to
a reward function trl.GRPOTrainer accepts as reward_funcs.
Exit: 0 completed, 75 paused-by-signal (checkpointed), 3 failed."""
import argparse
import importlib
import sys
from pathlib import Path

from forge import config
from forge.train import common


def _load_reward_fn(dotted_path):
    module_name, _, attr = dotted_path.rpartition(".")
    if not module_name:
        raise ValueError(f"params.reward_module must be a dotted path, got {dotted_path!r}")
    mod = importlib.import_module(module_name)
    return getattr(mod, attr)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--recipe", required=True)
    ap.add_argument("--run-dir", required=True)
    args = ap.parse_args(argv)

    recipe = common.read_recipe(args.recipe)
    p = recipe["params"]
    run_dir = Path(args.run_dir)
    ck_dir = run_dir / "checkpoints"

    reward_module = p.get("reward_module")
    if not reward_module:
        raise ValueError(
            "params.reward_module is required for GRPO: a dotted Python path "
            "under the repo root, e.g. rewards.length_penalty")
    reward_fn = _load_reward_fn(reward_module)

    flag = common.StopFlag()
    flag.install()

    from unsloth import FastLanguageModel  # import order matters for unsloth
    from datasets import load_dataset
    from trl import GRPOConfig, GRPOTrainer

    model_path = str(Path(config.MODEL_ROOT) / recipe["model_path"])
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=model_path,
        max_seq_length=p.get("max_seq_length", 2048),
        load_in_4bit=True,
    )
    model = FastLanguageModel.get_peft_model(
        model,
        r=p.get("lora_r", 16),
        lora_alpha=p.get("lora_alpha", 32),
        lora_dropout=0.05,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"],
        use_gradient_checkpointing="unsloth",
        random_state=42,
    )
    ds_path = p["dataset_path"].format(data_root=config.DATA_ROOT)
    ext = "json" if ds_path.endswith((".jsonl", ".json")) else "parquet"
    dataset = load_dataset(ext, data_files=ds_path, split="train")

    cfg = GRPOConfig(
        output_dir=str(ck_dir),
        per_device_train_batch_size=p.get("per_device_batch", 2),
        gradient_accumulation_steps=p.get("grad_accum", 8),
        learning_rate=p.get("learning_rate", 1e-6),
        lr_scheduler_type="cosine",
        weight_decay=0.01,
        bf16=True,
        optim="adamw_8bit",
        save_steps=p.get("save_steps", 250),
        save_total_limit=3,
        logging_steps=25,
        report_to="none",
        max_prompt_length=p.get("max_seq_length", 2048),
        num_generations=p.get("num_generations", 8),
    )
    trainer = GRPOTrainer(model=model, reward_funcs=reward_fn, processing_class=tokenizer,
                          train_dataset=dataset, args=cfg,
                          callbacks=[common.make_stop_callback(flag)])
    resume = common.latest_checkpoint(ck_dir)
    trainer.train(resume_from_checkpoint=str(resume) if resume else None)

    if flag.triggered:
        return common.EXIT_PAUSED
    adapter_dir = run_dir / "adapter"
    model.save_pretrained(str(adapter_dir))
    tokenizer.save_pretrained(str(adapter_dir))
    if recipe.get("push_to_hf"):
        model.push_to_hub(f"GoodAncestor/{recipe['name']}", private=True)
    return common.EXIT_OK


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:  # any training error → exit 3 for the runner
        print(f"FAILED: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(common.EXIT_JOB)
