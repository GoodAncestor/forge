# rocm profile — stub (locked when AMD hardware is first offered)

Same logical set as the CUDA profiles, with known substitutions:
- torch: install from the ROCm index (see profiles.yaml torch_index)
- flash-attn -> ROCm builds via aotriton/CK; verify current guidance at lock time
- bitsandbytes -> ROCm support is partial; QLoRA may need torchao or GPTQ paths
- unsloth -> check current ROCm support status before promising QLoRA parity
- deepspeed, trl, peft, transformers, datasets, accelerate -> expected to work as-is

To promote to `locked`: copy a CUDA profile pyproject, swap the index, fix the
substitutions above against current upstream docs, `uv lock`, run envs/smoke.py
on the AMD node, update profiles.yaml status.
