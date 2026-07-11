# forge TODO — path to v1 acceptance

Deployed state as of 2026-07-10 (see ops/cron.md "Deployed reality"): /opt/forge
live on the jumpbox, cron installed, `lease status` smoke green, and a full
lease acquire→release round-trip on ai02 verified LEASE_SECRET write auth.
TrueNAS HDD pool: 94.9T free of 98.2T — 50TB cap fits with the 20%-free rule.
Base model for the acceptance demo already on NAS: talkie-lm/talkie-1930-13b-base.

## Human (Colby)

1. **gh token on jumpbox.** Create a fine-grained PAT scoped to
   GoodAncestor/forge (Contents: read/write, Pull requests: read/write), then
   on the jumpbox: `echo <token> | gh auth login --with-token`
   (gh 2.96.0 already installed). Until then the weekly env update pushes its
   branch (write deploy key) but records `pr_error` instead of opening the PR.
2. **Flip `approved:` flags** in datasets/manifest.yaml via PR. The Talkie
   acceptance run needs the historical-1930-1980 tier: gutenberg-mirror,
   chronicling-america-1930-1963, wikipedia-en-dump. All 15 entries currently
   ship `approved: false`.
3. **Pick the acceptance 5090.** alien01/02/03 are all `safe_to_offline: yes`
   but each is serving a qwen3.6 model — the RUNBOOK forbids an agent picking
   a serving node. Either sign off on one (floor lease) or park its model.

## Agent (unblocked by the above)

4. After (2): `forge --json data fetch --tier historical-1930-1980` from a
   NAS-mounted node (sequential; jumpbox has no /mnt/models). Note
   /mnt/models/datasets does not exist yet — first fetch creates it.
5. After (4): build corpus-1930-1980/train.jsonl per GoodAncestor HQ
   knowledge/projects/historical-model-training.md (pipeline lives outside
   forge).
6. After (3+5): acceptance run
   `forge --json run recipes/talkie-1930to1980-qlora.yaml --host <node>`,
   including forced pause (SIGTERM → exit 75) and `--resume` verification.

## Agent (opportunistic)

7. Verify fleet HF token write-scope before any HF-org push — no HF token
   exists in the jumpbox fleet secrets today, so this is also a "locate or
   provision token" task.
8. On-node verification of REAP/heretic tool_cmd paths.
9. Known debt: gptqmodel>=5 floor caps env transformers at 4.57.2 / trl 0.24
   (consider a quantize-only env split); FSDP exit-75 pause propagation
   unverified until ai-silo.
