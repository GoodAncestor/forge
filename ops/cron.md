# forge scheduled operations (jumpbox)

Cron owns the schedule; Hermes reads the JSON reports and escalates.

    # /etc/cron.d/forge  (run as the forge service user; needs gh auth + FORGE_LEASE_SECRET)
    # weekly env update, Mondays 06:00 UTC
    0 6 * * 1  forge  cd /opt/forge && uv run forge --json env update >> /var/log/forge-env-update.log 2>&1
    # monthly manifest size refresh, 1st 06:30 UTC
    30 6 1 * * forge  cd /opt/forge && uv run forge --json data sizes --write >> /var/log/forge-data-sizes.log 2>&1

Reports land in /opt/forge/reports/env-update-YYYY-MM-DD.json.
Hermes check: newest report `ok: true` and younger than 8 days; else escalate.
