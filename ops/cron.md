# forge scheduled operations (jumpbox)

Cron owns the schedule; Hermes reads the JSON reports and escalates.

    # /etc/cron.d/forge  (run as the forge service user; needs gh auth + FORGE_LEASE_SECRET)
    # weekly env update, Mondays 06:00 UTC
    0 6 * * 1  forge  cd /opt/forge && uv run forge --json env update >> /var/log/forge-env-update.log 2>&1
    # monthly manifest size refresh (report-only — see note below), 1st 06:30 UTC
    30 6 1 * * forge  cd /opt/forge && uv run forge --json data sizes >> /var/log/forge-data-sizes.log 2>&1

Reports land in /opt/forge/reports/env-update-YYYY-MM-DD.json.
Hermes check: newest report `ok: true` and younger than 8 days; else escalate.

The monthly job runs WITHOUT `--write`: it measures and logs current sizes but
never rewrites datasets/manifest.yaml unattended. This is a deliberate
deferral of the spec's auto-PR-on-size-drift behavior — size drift shows up
in the JSON output/log; applying it is a human-reviewed PR: run
`forge data sizes --write` on a branch and open a PR (same never-auto-merge
rule as env updates).
