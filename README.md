# forge — an agent-operated model lab

**forge** is the toolkit the Good Ancestor Foundation uses to run its own model
work on its own hardware: preparing per-GPU-class training environments,
maintaining a governed dataset archive, and executing training, fine-tuning,
quantization, and model-surgery jobs safely on a shared GPU fleet.

It is designed to be driven by autonomous agents but governed by humans. Agents
do the mechanical work — resolving environments, fetching approved datasets,
launching leased runs. Humans do exactly two things: **review pull requests**
and **flip `approved:` flags**. Nothing consequential happens without a human in
that loop.

## Why it exists

Running models on a real fleet involves a lot of fiddly, error-prone work: which
CUDA/torch stack matches which GPU generation, which datasets are cleared for
use, whether a GPU is free or serving production, whether a job checkpointed
before it was killed. forge encodes all of that as small, testable,
single-purpose commands with machine-readable output — so an agent can operate
the fleet without improvising, and so every consequential step leaves an
auditable artifact.

## What's in the box

- **Per-GPU-class environments.** Each hardware class (e.g. Ada, Blackwell,
  datacenter) is its own isolated project with its own pinned lockfile, so the
  torch/CUDA stack always matches the silicon. A weekly job re-resolves the
  locks and opens a PR; hardware smoke-tests run on the target GPU before a
  human merges.
- **A governed dataset archive.** A single `manifest.yaml` is the source of
  truth for every dataset: its source, license, size, storage path, and an
  `approved:` flag that only a human flips. Fetches are refused for anything
  unapproved, oversized against a cap, or of unknown size — no silent
  workarounds.
- **Lease-safe runs.** Every training/quant/surgery job runs under a fleet lease
  with a heartbeat, so two agents never contend for the same GPU, and a job that
  touches a production-serving node is flagged loudly. Runs are resumable and
  record a signed manifest of exactly what happened.
- **Recipes.** Declarative YAML recipes for the common jobs — LoRA SFT, DPO,
  GRPO, AWQ/GGUF/NVFP4 quantization, abliteration, and expert pruning — each
  pinned to the environment profile it needs.

## Quick start

```sh
uv sync                      # install the CLI + dev deps
uv run forge --help
uv run pytest -q             # run the test suite
```

## The CLI

Everything is one `forge` command with a few subcommands. Add `--json` to any of
them for machine-readable output (this is how agents drive it).

```sh
forge env update                     # re-resolve env lockfiles, open a PR
forge data list                      # what datasets exist / are approved
forge data sizes                     # measure sizes against the cap
forge data fetch <name>              # fetch one approved dataset (resumable)
forge run recipes/sft-lora.yaml \    # run a recipe under a fleet lease
    --host <gpu-host> --profile <profile>
forge lease status                   # who holds which GPU right now
```

## The safety model

forge is opinionated about not doing damage:

- **Approval gates are final.** An unapproved or refused dataset fetch exits
  non-zero and stays refused until a human edits `approved:` via a reviewed PR.
  Agents do not work around the gate.
- **Automated PRs are never auto-merged.** The weekly environment update opens a
  PR and stops. A human reviews it, runs the hardware smoke-test, and merges.
- **Leases before GPUs.** Nothing runs on a GPU it hasn't leased, and jobs warn
  before touching a node that's serving production traffic.
- **Honest exit codes.** Commands distinguish "refused" (2), "job failed" (3),
  "infrastructure unreachable" (4), and "checkpointed/paused" (75), so callers —
  human or agent — never mistake one failure for another.

## Repository layout

```
src/forge/        # the CLI and its modules (env, data, run, lease, envupdate)
envs/             # one uv project per GPU class, each with its own lockfile
datasets/         # manifest.yaml — the governed dataset archive
recipes/          # declarative job recipes (sft, dpo, grpo, quantize, ...)
rewards/          # reward functions for preference/RL recipes
bootstrap/        # scripts that prepare a fresh GPU node
ops/              # operational notes (scheduling, etc.)
RUNBOOK.md        # the operator's guide (read this if you're driving forge)
```

## For humans

If you're a person looking at this repo, your job is small and well-defined:

1. **Review PRs** — especially environment-update PRs (check the version diff and
   run the smoke command the PR body gives you) and any PR that flips a dataset
   `approved:` flag.
2. **Decide what's approved** — you own the `approved:` flags in
   `datasets/manifest.yaml`. Agents propose; you dispose.

That's the whole job. Everything else is mechanical, tested, and automated.

## Status

forge is used in production by the Good Ancestor Foundation. It is shared here in
the spirit of the Foundation's mission — helping others stand up their own local,
sovereign AI infrastructure. Interfaces may change; the safety principles above
will not.
