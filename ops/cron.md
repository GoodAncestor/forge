# forge scheduled operations (jumpbox)

Cron owns the schedule; Hermes reads the JSON reports and escalates.

    # /etc/cron.d/forge  (run as the forge service user; needs gh auth + FORGE_LEASE_SECRET)
    # weekly env update, Mondays 06:00 UTC
    0 6 * * 1  forge  cd /opt/forge && uv run forge --json env update >> /var/log/forge-env-update.log 2>&1
    # monthly manifest size refresh (report-only — see note below), 1st 06:30 UTC
    30 6 1 * * forge  cd /opt/forge && uv run forge --json data sizes >> /var/log/forge-data-sizes.log 2>&1

## Deployed reality (jumpbox, 2026-07-10)
The jumpbox is Alpine/busybox crond: no /etc/cron.d support and no per-line
env, so the lines above are installed in /etc/crontabs/root via
/usr/local/bin/forge-cron — a wrapper that loads FORGE_LEASE_SECRET from
/root/.fleet-secrets (LEASE_SECRET key) and runs as root, consistent with the
other jumpbox services (same adaptation the fleet-aggregator openrc unit
documents). GitHub access is a write deploy key (/root/.ssh/forge-deploy,
Host github-forge). Known gap: `gh` is not installed/authed on the jumpbox,
so the weekly env update will record pr_error instead of opening the PR
until a repo-scoped token is provisioned (human task).

Reports land in /opt/forge/reports/env-update-YYYY-MM-DD.json.
Hermes check: newest report `ok: true` and younger than 8 days; else escalate.

The monthly job runs WITHOUT `--write`: it measures and logs current sizes but
never rewrites datasets/manifest.yaml unattended. This is a deliberate
deferral of the spec's auto-PR-on-size-drift behavior — size drift shows up
in the JSON output/log; applying it is a human-reviewed PR: run
`forge data sizes --write` on a branch and open a PR (same never-auto-merge
rule as env updates).
