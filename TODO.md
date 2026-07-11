# forge TODO — path to v1 acceptance

Deployed state as of 2026-07-10 (see ops/cron.md "Deployed reality"): /opt/forge
live on the jumpbox, cron installed, `lease status` smoke green, and a full
lease acquire→release round-trip on ai02 verified LEASE_SECRET write auth.
TrueNAS HDD pool: 94.9T free of 98.2T — 50TB cap fits with the 20%-free rule.
Base model for the acceptance demo already on NAS: talkie-lm/talkie-1930-13b-base.

Update 2026-07-10 (Colby): downloads approved — all manifest entries flipped
`approved: true` (6913aca) and the fetch queue is RUNNING on ai02 (tmux
session `forge-fetch`, log ~/forge-fetch.log, FORGE_DATA_ROOT=
/mnt/truenas-models/datasets — NOTE: on ai02 the TrueNAS share mounts at
/mnt/truenas-models, not the forge default /mnt/models, which is a stale
fstab entry for the Alameda NAS). Queue: historical tier → small sets →
fineweb-edu + dclm-baseline (~13TB tail). Resumable: rerun
~/forge-fetch-queue.sh. Infra changes (model parking, 5090 acceptance run)
explicitly DEFERRED by Colby — do not bring anything up.

## Human (Colby)

1. **gh token on jumpbox.** Create a fine-grained PAT scoped to
   GoodAncestor/forge (Contents: read/write, Pull requests: read/write), then
   on the jumpbox: `echo <token> | gh auth login --with-token`
   (gh 2.96.0 already installed). Until then the weekly env update pushes its
   branch (write deploy key) but records `pr_error` instead of opening the PR.
2. **HF token for gated datasets** — nemotron-cc (NVIDIA Data Agreement,
   gated:manual) and lmsys-chat-1m (gated:auto) are approved but excluded
   from the running queue; they need a token whose account accepted terms.
3. **DEFERRED until you reopen infra work: pick the acceptance 5090.**
   alien01/02/03 are all `safe_to_offline: yes` but each serves a qwen3.6
   model — the RUNBOOK forbids an agent picking a serving node. Either sign
   off on one (floor lease) or park its model.

## Agent (unblocked by the above)

4. When the historical tier lands: build corpus-1930-1980/train.jsonl per
   GoodAncestor HQ knowledge/projects/historical-model-training.md (pipeline
   lives outside forge). Base model already on NAS.
5. After (3+4): acceptance run
   `forge --json run recipes/talkie-1930to1980-qlora.yaml --host <node>`,
   including forced pause (SIGTERM → exit 75) and `--resume` verification.
6. Consider a manifest/docs note or env default fix for the /mnt/models vs
   /mnt/truenas-models path mismatch on Berkeley nodes.

## Agent (opportunistic)

7. Verify fleet HF token write-scope before any HF-org push — no HF token
   exists in the jumpbox fleet secrets today, so this is also a "locate or
   provision token" task.
8. On-node verification of REAP/heretic tool_cmd paths.
9. Known debt: gptqmodel>=5 floor caps env transformers at 4.57.2 / trl 0.24
   (consider a quantize-only env split); FSDP exit-75 pause propagation
   unverified until ai-silo.
