import requests

from forge import config


class LeaseRefused(Exception):
    """Server refused (409 invariant / 400 malformed). .args[0] is the reason."""


class FleetUnreachable(Exception):
    """Network-level failure talking to the aggregator."""


class LeaseClient:
    def __init__(self, base_url=None, secret=None, timeout=10):
        self.base_url = (base_url or config.FLEET_URL).rstrip("/")
        self.secret = config.LEASE_SECRET if secret is None else secret
        self.timeout = timeout

    def _post(self, path, body):
        try:
            r = requests.post(self.base_url + path, json=body,
                              headers={"Authorization": f"Bearer {self.secret}"},
                              timeout=self.timeout)
        except requests.RequestException as e:
            raise FleetUnreachable(str(e)) from e
        if r.status_code in (400, 401, 403, 409):
            try:
                reason = r.json().get("error", r.text)
            except ValueError:
                reason = r.text
            raise LeaseRefused(reason)
        r.raise_for_status()
        return r.json()

    def acquire(self, holder, target_type, name, mode="exclusive",
                ttl_sec=28800, notes="", min_floor=None):
        target = {"type": target_type, "name": name}
        if min_floor is not None:
            target["min_floor"] = min_floor
        body = {"holder": holder, "mode": mode, "target": target,
                "ttl_sec": ttl_sec, "notes": notes}
        return self._post("/leases/acquire", body)["lease"]

    def renew(self, lease_id, ttl_sec=28800):
        return self._post("/leases/renew", {"id": lease_id, "ttl_sec": ttl_sec})["lease"]

    def release(self, lease_id):
        return bool(self._post("/leases/release", {"id": lease_id}).get("existed"))

    def fleet(self):
        try:
            r = requests.get(self.base_url + "/fleet.json", timeout=self.timeout)
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            raise FleetUnreachable(str(e)) from e

    def node(self, name):
        for n in self.fleet().get("nodes", []):
            if n.get("name") == name:
                return n
        return None
