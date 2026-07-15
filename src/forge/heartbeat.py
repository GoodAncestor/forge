import threading


class LeaseHeartbeat:
    """Renews a lease every interval_sec. One failed renew gets one retry after
    retry_wait; a second failure sets .lost — the runner must then checkpoint
    and stop the job. Daemon thread; .stop() is idempotent."""

    def __init__(self, client, lease_id, ttl_sec=28800, interval_sec=7200, retry_wait=60):
        self._client = client
        self._lease_id = lease_id
        self._ttl = ttl_sec
        self._interval = interval_sec
        self._retry_wait = retry_wait
        self.lost = threading.Event()
        self._stop_evt = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True,
                                        name=f"lease-heartbeat-{lease_id[:8]}")

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop_evt.set()
        if self._thread.is_alive():
            self._thread.join(timeout=5)

    def _renew_once(self):
        self._client.renew(self._lease_id, self._ttl)

    def _loop(self):
        while not self._stop_evt.wait(self._interval):
            try:
                self._renew_once()
                continue
            except Exception:
                pass
            if self._stop_evt.wait(self._retry_wait):
                return
            try:
                self._renew_once()
            except Exception:
                self.lost.set()
                return
