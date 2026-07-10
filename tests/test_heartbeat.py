import time

from forge.heartbeat import LeaseHeartbeat
from forge.lease import LeaseRefused


class GoodClient:
    def __init__(self):
        self.renews = 0

    def renew(self, lease_id, ttl_sec):
        self.renews += 1
        return {"id": lease_id}


class BadClient:
    def renew(self, lease_id, ttl_sec):
        raise LeaseRefused("no active lease with id x")


def test_renews_periodically():
    c = GoodClient()
    hb = LeaseHeartbeat(c, "x", ttl_sec=10, interval_sec=0.05, retry_wait=0.01)
    hb.start()
    time.sleep(0.2)
    hb.stop()
    assert c.renews >= 2
    assert not hb.lost.is_set()


def test_sets_lost_after_retry_fails():
    hb = LeaseHeartbeat(BadClient(), "x", ttl_sec=10, interval_sec=0.05, retry_wait=0.01)
    hb.start()
    assert hb.lost.wait(timeout=2), "lost should be set after failed renew + retry"
    hb.stop()


def test_stop_is_clean_and_idempotent():
    c = GoodClient()
    hb = LeaseHeartbeat(c, "x", ttl_sec=10, interval_sec=0.05)
    hb.start()
    hb.stop()
    hb.stop()
