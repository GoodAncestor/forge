# forge scheduled operations

Cron owns the schedule; an operator (human or agent) reads the JSON reports
and escalates. Both jobs need `FORGE_LEASE_SECRET`, a `GH_TOKEN` (or `gh auth`)
for opening PRs, and push access to the repo.

    # weekly env update, Mondays 06:00 UTC
    0 6 * * 1  cd <forge> && uv run forge --json env update >> env-update.log 2>&1
    # monthly manifest size refresh (report-only — see note below), 1st 06:30 UTC
    30 6 1 * *  cd <forge> && uv run forge --json data sizes >> data-sizes.log 2>&1

Deployment specifics (which user, where secrets/keys live, any busybox-crond
wrapper) are environment-dependent and kept in your private fleet config, not
here. The env-update job runs wherever the cron lives and needs no GPU: it only
re-resolves the lockfiles and opens a PR (hardware smoke is deferred to the
reviewer — see RUNBOOK "Env maintenance").

Reports land in `reports/env-update-YYYY-MM-DD.json`. Monitor check: newest
report `ok: true` and younger than 8 days; else escalate.

The monthly job runs WITHOUT `--write`: it measures and logs current sizes but
never rewrites datasets/manifest.yaml unattended. This is a deliberate
deferral of the spec's auto-PR-on-size-drift behavior — size drift shows up
in the JSON output/log; applying it is a human-reviewed PR: run
`forge data sizes --write` on a branch and open a PR (same never-auto-merge
rule as env updates).
