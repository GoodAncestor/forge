# forge RUNBOOK — for LLM operators

You are operating the Good Ancestor model lab. Everything below is CLI + JSON.
Humans only: merge PRs, flip `approved:` flags, sign off on production-node runs.

## Environment
- Aggregator/fleet state: GET $FORGE_FLEET_URL/fleet.json (set FORGE_FLEET_URL
  to your aggregator; default http://localhost:8096)
- FORGE_FLEET_CONFIG: path to the private fleet overlay (profiles.hosts.yaml)
  that binds each profile to real hosts. Unset → profiles have no hosts.
- Required env: FORGE_LEASE_SECRET (from your fleet secrets). Optional:
  FORGE_DATA_ROOT (/mnt/models/datasets), FORGE_MODEL_ROOT (/mnt/models),
  FORGE_DATA_CAP_TB (50 — meters the dataset subtree only, NOT the models sharing
  the pool; the practical ceiling is pool free space — keep ZFS ~20% free),
  FORGE_HOLDER (identify yourself: e.g. forge@hermes-task-123)
- Exit codes everywhere: 0 ok · 2 refused · 3 job failure · 4 infra unreachable · 75 paused/checkpointed
- Status posts: with FORGE_FLEET_URL + FORGE_LEASE_SECRET set, fetches and runs
  push fire-and-forget progress to $FORGE_FLEET_URL/forge/status, feeding the
  read-only /forge panel on the jumpbox. Never blocks or fails a job. All
  secret holders share one status namespace (kind,host,id — latest wins);
  run terminal docs are one-shot and prune after 7 days — run.json on disk
  stays the durable record.

## Choosing a node
1. `forge --json lease status` — see held_by and serving per node.
2. Read fleet.json: prefer nodes with `safe_to_offline_for_build.ok == true`
   and empty `serving`. NEVER pick a serving node without a floor lease + human sign-off.
3. Map host → profile: `forge --json env list` (profiles carry a hosts list).

## Running a job
    forge --json run recipes/<recipe>.yaml --host <node>
- The runner leases the node, heartbeats, launches under the profile env,
  and releases on exit. Logs: <run_dir>/job.log; manifest: <run_dir>/run.json.
- Exit 75 = paused (lease lost or interrupted) — the job checkpointed itself.
  To RESUME: confirm `<run_dir>/checkpoints/checkpoint-N` exists, then:
      forge --json run <recipe> --host <node> --resume <run_dir>
  `--resume` reuses that exact run dir instead of creating a fresh one
  (lease, heartbeat, and recipe are otherwise unchanged) — the trainers
  auto-resume from the latest checkpoint in it. Never start a fresh run dir
  when a checkpoint exists; you'd retrain from step 0.
- Off-fleet (rented/loaner) node: bootstrap/ephemeral-node.sh first, then add
  --off-fleet. Push artifacts back to the NAS before the node dies.

## Long runs (multi-day)
- Leases cap at 24h server-side; forge acquires 8h and renews every 2h
  automatically. You do nothing. If the aggregator is down >2 renew cycles the
  run pauses itself (exit 75) — resume once the aggregator is back.

## Datasets
    forge --json data list            # what exists, what's approved
    forge --json data sizes           # measured sizes vs cap (network)
    forge --json data fetch --tier sft-preference --dry-run
    forge --json data fetch <name>    # approved entries only; sequential
    forge --json data report          # what's actually on disk
- Refusals (exit 2) are final unless a human flips `approved:` in
  datasets/manifest.yaml via PR. Do not work around the gate.

## Env maintenance
    forge --json env update           # re-resolve lockfiles + open PR
- Weekly cron does this. It runs where the cron lives (no GPU needed): it only
  re-resolves the locks and opens a PR. `ok` = locks resolved cleanly.
- Hardware smoke is deferred to PR review: the PR body carries the exact
  `forge run recipes/smoke.yaml ...` command to run on each profile's
  smoke_host before merging. Read reports/env-update-*.json; escalate if
  ok=false (a lock failed to resolve).
- NEVER merge the PR yourself.

## Safety rails you must respect
- One purposeful connection at a time to any host (network IPS blocks scanners).
- Never modify NAS config. Never download unapproved models/datasets.
- Some nodes serve production inference: floor lease + human sign-off before
  touching a node whose `serving` list is non-empty.
- Abliterated/pruned artifacts: NAS only, never push to HF.
