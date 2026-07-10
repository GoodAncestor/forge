# forge RUNBOOK — for LLM operators

You are operating the Good Ancestor model lab. Everything below is CLI + JSON.
Humans only: merge PRs, flip `approved:` flags, sign off on production-node runs.

## Environment
- Aggregator/fleet state: GET $FORGE_FLEET_URL/fleet.json (default http://192.168.77.36:8096)
- Required env: FORGE_LEASE_SECRET (from jumpbox fleet secrets). Optional:
  FORGE_DATA_ROOT (/mnt/models/datasets), FORGE_MODEL_ROOT (/mnt/models),
  FORGE_DATA_CAP_TB (20), FORGE_HOLDER (identify yourself: e.g. forge@hermes-task-123)
- Exit codes everywhere: 0 ok · 2 refused · 3 job failure · 4 infra unreachable · 75 paused/checkpointed

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
  To RESUME: confirm `<run_dir>/checkpoints/checkpoint-N` exists, then re-invoke
  the entrypoint against the SAME run dir:
      forge --json run <same recipe> --host <node> --run-root <same run_dir parent>
  and if the runner created a fresh timestamped dir, instead run the entrypoint
  directly with `--run-dir <original run_dir>` under the profile env — the
  trainers auto-resume from the latest checkpoint in that dir. Never start a
  fresh run dir when a checkpoint exists; you'd retrain from step 0.
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
    forge --json env update           # lock upgrade + leased smoke + PR
- Weekly cron does this. Read reports/env-update-*.json; escalate if ok=false.
- NEVER merge the PR yourself.

## Safety rails you must respect
- One purposeful connection at a time to any host (UniFi IPS blocks scanners).
- Never modify NAS config. Never download unapproved models/datasets.
- ai-silo serves production: floor lease + human sign-off before touching it.
- Abliterated/pruned artifacts: NAS only, never push to HF.
