# Store/src/app/darwin_client.py
"""
Darwin telemetry client - self-reporting middleware.

Streams topology and metrics to the Darwin BlackBoard brain.
Runs as a background thread, pushing telemetry every 5 seconds.
"""

import os
import re
import socket
import time
import logging
import threading
from typing import Optional

import psutil
import requests

from .models import TelemetryPayload, Metrics, Dependency, Topology, GitOpsMetadata
from .chaos_state import get_error_rate

# GitOps metadata from environment (set in Dockerfile or Helm)
GITOPS_REPO = os.getenv("GITOPS_REPO")      # e.g., "The-Darwin-Project/Store"
GITOPS_REPO_URL = os.getenv("GITOPS_REPO_URL")  # e.g., "https://github.com/The-Darwin-Project/Store.git"
HELM_PATH = os.getenv("HELM_PATH")          # e.g., "helm/values.yaml"

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
        """Build the telemetry payload with current metrics, topology, and GitOps metadata."""
        metrics = self._collect_metrics()
        dependencies = self._discover_topology()
        gitops = self._build_gitops_metadata()
        pod_ips = self._collect_pod_ips()
        
        return TelemetryPayload(
            service=self.service,
            version=self.version,
            metrics=metrics,
            topology=Topology(dependencies=dependencies),
            gitops=gitops,
            pod_ips=pod_ips
        )
    
    def _build_gitops_metadata(self) -> Optional[GitOpsMetadata]:
        """Build GitOps metadata from environment variables."""
        if not GITOPS_REPO:
            return None
        
        return GitOpsMetadata(
            repo=GITOPS_REPO,
            repo_url=GITOPS_REPO_URL,
            helm_path=HELM_PATH
        )
    
    def _collect_pod_ips(self) -> list[str]:
        """
        Collect pod IP addresses for IP-to-name correlation.
        
        Uses HOSTNAME env var (reliable in K8s) with socket fallback.
        This allows the BlackBoard to correlate IP-based dependency targets
        with named services, eliminating duplicate nodes in the graph.
        """
        ips = []
        
        # Primary: HOSTNAME env var (set by K8s to pod name, resolvable via DNS)
        hostname = os.getenv("HOSTNAME")
        if hostname:
            try:
                ip = socket.gethostbyname(hostname)
                if ip and not ip.startswith("127."):
                    ips.append(ip)
            except socket.gaierror:
                pass
        
        # Fallback: socket.gethostname()
        if not ips:
            try:
                ip = socket.gethostbyname(socket.gethostname())
                if ip and not ip.startswith("127."):
                    ips.append(ip)
            except socket.gaierror:
                pass
        
        return ips
    
    # State for cgroup CPU calculation
    _last_cpu_usage: float = 0.0
    _last_cpu_time: float = 0.0
    
    def _get_cgroup_cpu_percent(self) -> float:
        """
        Get CPU usage from cgroup stats for accurate container metrics.
        
        Falls back to psutil if cgroup stats aren't available.
        Uses cumulative CPU time delta for smooth, consistent readings.
        """
        try:
            # Try cgroup v2 first (modern containers)
            cpu_stat_path = "/sys/fs/cgroup/cpu.stat"
            if os.path.exists(cpu_stat_path):
                with open(cpu_stat_path, "r") as f:
                    for line in f:
                        if line.startswith("usage_usec"):
                            cpu_usec = float(line.split()[1])
                            break
                    else:
                        raise ValueError("usage_usec not found")
                
                current_time = time.time()
                
                # First reading - initialize and return psutil as fallback
                if self._last_cpu_time == 0:
                    self._last_cpu_usage = cpu_usec
                    self._last_cpu_time = current_time
                    return psutil.cpu_percent(interval=0.1)
                
                # Calculate CPU percentage from delta
                time_delta = current_time - self._last_cpu_time
                if time_delta > 0:
                    # Convert microseconds to seconds, divide by time delta
                    # Multiply by 100 for percentage, divide by number of CPUs
                    cpu_delta = (cpu_usec - self._last_cpu_usage) / 1_000_000
                    cpu_count = os.cpu_count() or 1
                    cpu_percent = (cpu_delta / time_delta / cpu_count) * 100
                    
                    # Update state for next reading
                    self._last_cpu_usage = cpu_usec
                    self._last_cpu_time = current_time
                    
                    return min(cpu_percent, 100.0)  # Cap at 100%
            
            # Try cgroup v1 (older containers)
            cpuacct_path = "/sys/fs/cgroup/cpu/cpuacct.usage"
            if os.path.exists(cpuacct_path):
                with open(cpuacct_path, "r") as f:
                    cpu_ns = float(f.read().strip())
                
                current_time = time.time()
                
                if self._last_cpu_time == 0:
                    self._last_cpu_usage = cpu_ns
                    self._last_cpu_time = current_time
                    return psutil.cpu_percent(interval=0.1)
                
                time_delta = current_time - self._last_cpu_time
                if time_delta > 0:
                    cpu_delta = (cpu_ns - self._last_cpu_usage) / 1_000_000_000
                    cpu_count = os.cpu_count() or 1
                    cpu_percent = (cpu_delta / time_delta / cpu_count) * 100
                    
                    self._last_cpu_usage = cpu_ns
                    self._last_cpu_time = current_time
                    
                    return min(cpu_percent, 100.0)
        
        except Exception as e:
            logger.debug(f"Cgroup CPU read failed, using psutil: {e}")
        
        # Fallback to psutil (non-blocking for smoother readings)
        return psutil.cpu_percent(interval=0.1)
    
    def _collect_metrics(self) -> Metrics:
        """Collect current system metrics."""
        # Use cgroup stats for accurate container CPU (avoids psutil spikiness)
        cpu = self._get_cgroup_cpu_percent()
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
