# forge — Good Ancestor model lab

Agent-operated toolkit: per-GPU-class training environments, NAS dataset
archive, lease-safe training runs, and model-surgery recipes.

- Spec: GoodAncestor HQ `docs/superpowers/specs/2026-07-10-forge-design.md`
- Operators (LLM): read `RUNBOOK.md`
- Humans: you review PRs and flip `approved:` flags; that's the whole job.

## Quick start
    uv sync                      # CLI + dev deps
    uv run forge --help
    uv run pytest -q
