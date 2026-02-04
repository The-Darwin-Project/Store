import os, time, psutil, requests, threading
class DarwinClient:
    def __init__(self, service, url):
        self.svc = service
        self.url = url
        threading.Thread(target=self._loop, daemon=True).start()
    
    def _loop(self):
        while True:
            try:
                # Todo: Add Topology Discovery
                requests.post(f"{self.url}/telemetry", json={"service": self.svc, "status": "alive"})
            except: pass
            time.sleep(5)
