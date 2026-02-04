# Store/src/app/darwin_client.py
"""
Darwin telemetry client - self-reporting middleware.

Streams topology and metrics to the Darwin BlackBoard brain.
Runs as a background thread, pushing telemetry every 5 seconds.
"""

import os
import re
import time
import logging
import threading
from typing import Optional

import psutil
import requests

from .models import TelemetryPayload, Metrics, Dependency, Topology
from .chaos_state import get_error_rate

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DarwinClient:
    """Self-reporting client that streams telemetry to Darwin BlackBoard."""
    
    def __init__(self, service: str, url: str, version: str = "1.0.0"):
        """
        Initialize the Darwin client.
        
        Args:
            service: Service name (e.g., "darwin-store")
            url: Darwin BlackBoard URL (e.g., "http://darwin-blackboard:8000")
            version: Service version for telemetry
        """
        self.service = service
        self.url = url
        self.version = version
        self._stop_flag = threading.Event()
        self._thread: Optional[threading.Thread] = None
    
    def start(self) -> None:
        """Start the telemetry background thread."""
        if self._thread and self._thread.is_alive():
            logger.warning("DarwinClient already running")
            return
        
        self._stop_flag.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info(f"DarwinClient started for {self.service} -> {self.url}")
    
    def stop(self) -> None:
        """Stop the telemetry background thread."""
        self._stop_flag.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        logger.info("DarwinClient stopped")
    
    def _loop(self) -> None:
        """Main telemetry loop - runs every 5 seconds."""
        while not self._stop_flag.is_set():
            try:
                payload = self._build_payload()
                self._send_telemetry(payload)
            except Exception as e:
                # Graceful failure - log and continue
                logger.warning(f"Telemetry failed: {e}")
            
            # Sleep in small increments to allow faster shutdown
            for _ in range(50):
                if self._stop_flag.is_set():
                    return
                time.sleep(0.1)
    
    def _build_payload(self) -> TelemetryPayload:
        """Build the telemetry payload with current metrics and topology."""
        metrics = self._collect_metrics()
        dependencies = self._discover_topology()
        
        return TelemetryPayload(
            service=self.service,
            version=self.version,
            metrics=metrics,
            topology=Topology(dependencies=dependencies)
        )
    
    def _collect_metrics(self) -> Metrics:
        """Collect current system metrics."""
        # psutil.cpu_percent captures container-wide CPU (not just this process)
        cpu = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory().percent
        error_rate = get_error_rate()
        
        return Metrics(
            cpu=cpu,
            memory=memory,
            error_rate=error_rate
        )
    
    def _discover_topology(self) -> list[Dependency]:
        """
        Discover service dependencies by scanning environment variables.
        
        CRITICAL: Returns the env var KEY name (e.g., DATABASE_URL), not just the value.
        The SysAdmin Agent needs the key name to construct kubectl patch commands.
        """
        dependencies = []
        
        # Patterns for different dependency types
        db_patterns = [
            r'^DATABASE_.*',
            r'^DB_.*',
            r'^POSTGRES_.*',
            r'^MYSQL_.*',
            r'^REDIS_.*',
        ]
        
        http_patterns = [
            r'.*_HOST$',
            r'.*_URL$',
            r'.*_URI$',
            r'.*_ENDPOINT$',
        ]
        
        for key, value in os.environ.items():
            # Skip empty values
            if not value:
                continue
            
            # Check for database dependencies
            for pattern in db_patterns:
                if re.match(pattern, key, re.IGNORECASE):
                    dependencies.append(Dependency(
                        target=self._extract_target(value),
                        type="db",
                        env_var=key  # The KEY name for SysAdmin patching
                    ))
                    break
            else:
                # Check for HTTP dependencies
                for pattern in http_patterns:
                    if re.match(pattern, key, re.IGNORECASE):
                        dependencies.append(Dependency(
                            target=self._extract_target(value),
                            type="http",
                            env_var=key  # The KEY name for SysAdmin patching
                        ))
                        break
        
        return dependencies
    
    def _extract_target(self, value: str) -> str:
        """Extract a readable target name from a URL or connection string."""
        # Try to extract hostname from URLs
        if "://" in value:
            # Remove protocol
            remainder = value.split("://", 1)[1]
            # Get host part (before path or port)
            host = remainder.split("/")[0].split(":")[0].split("@")[-1]
            return host
        
        # For simple hostnames, return as-is
        return value.split(":")[0]
    
    def _send_telemetry(self, payload: TelemetryPayload) -> None:
        """Send telemetry to Darwin BlackBoard."""
        if not self.url:
            return
        
        endpoint = f"{self.url.rstrip('/')}/telemetry/"
        
        response = requests.post(
            endpoint,
            json=payload.model_dump(),
            timeout=5.0
        )
        
        if response.status_code >= 400:
            logger.warning(f"Telemetry rejected: {response.status_code}")
        else:
            logger.debug(f"Telemetry sent: {payload.service}")
