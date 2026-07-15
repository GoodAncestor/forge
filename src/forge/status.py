"""Fire-and-forget status posts to the fleet aggregator's /forge/status.

Feeds the read-only /forge panel on the jumpbox. A status post must NEVER
fail or slow a download or run: 2s timeout, every exception swallowed, and a
silent no-op when FORGE_LEASE_SECRET is unset (forge behaves exactly as
before this module existed). No retries — the next tick supersedes.
"""
import datetime
import socket

import requests

from forge import config

TIMEOUT = 2.0


def enabled():
    return bool(config.FLEET_URL and config.LEASE_SECRET)


def post(kind, id, state, payload=None):
    """Best-effort push. True only if the aggregator acked with a 2xx."""
    if not enabled():
        return False
    doc = {"v": 1, "kind": kind, "host": socket.gethostname(), "id": id,
           "state": state,
           "ts": datetime.datetime.now(datetime.timezone.utc)
                                  .strftime("%Y-%m-%dT%H:%M:%SZ"),
           "payload": payload or {}}
    try:
        r = requests.post(config.FLEET_URL + "/forge/status", json=doc,
                          headers={"Authorization":
                                   f"Bearer {config.LEASE_SECRET}"},
                          timeout=TIMEOUT)
        return 200 <= r.status_code < 300
    except Exception:
        return False
