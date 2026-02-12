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
    
    def __init__(self, service: str, url: str, version: str = "1.0.0", read_timeout: float = 30.0):
        """
        Initialize the Darwin client.
        
        Args:
            service: Service name (e.g., "darwin-store")
            url: Darwin BlackBoard URL (e.g., "http://darwin-blackboard:8000")
            version: Service version for telemetry
            read_timeout: Read timeout for telemetry requests
        """
        self.service = service
        self.url = url
        self.version = version
        self.read_timeout = read_timeout
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
    
    # Cache for container CPU limit (read once)
    _cpu_limit_cores: float = 0.0

    def _get_cpu_limit_cores(self) -> float:
        """
        Get the container's CPU limit in cores from cgroup.
        
        Reads cgroup v2 cpu.max or cgroup v1 cpu.cfs_quota_us/cpu.cfs_period_us.
        Falls back to os.cpu_count() if no limit is set (unlimited container).
        """
        if self._cpu_limit_cores > 0:
            return self._cpu_limit_cores

        try:
            # cgroup v2: cpu.max contains "quota period" (e.g., "100000 100000" = 1 core)
            cpu_max_path = "/sys/fs/cgroup/cpu.max"
            if os.path.exists(cpu_max_path):
                with open(cpu_max_path, "r") as f:
                    parts = f.read().strip().split()
                    if parts[0] == "max":
                        # No limit set
                        self._cpu_limit_cores = float(os.cpu_count() or 1)
                    else:
                        quota = float(parts[0])
                        period = float(parts[1]) if len(parts) > 1 else 100000.0
                        self._cpu_limit_cores = quota / period
                    return self._cpu_limit_cores

            # cgroup v1: cpu.cfs_quota_us / cpu.cfs_period_us
            quota_path = "/sys/fs/cgroup/cpu/cpu.cfs_quota_us"
            period_path = "/sys/fs/cgroup/cpu/cpu.cfs_period_us"
            if os.path.exists(quota_path) and os.path.exists(period_path):
                with open(quota_path, "r") as f:
                    quota = float(f.read().strip())
                with open(period_path, "r") as f:
                    period = float(f.read().strip())
                if quota < 0:
                    # No limit set (-1)
                    self._cpu_limit_cores = float(os.cpu_count() or 1)
                else:
                    self._cpu_limit_cores = quota / period
                return self._cpu_limit_cores

        except Exception as e:
            logger.debug(f"Failed to read CPU limit from cgroup: {e}")

        # Fallback: host CPU count (inaccurate for limited containers)
        self._cpu_limit_cores = float(os.cpu_count() or 1)
        return self._cpu_limit_cores

    def _get_cgroup_cpu_percent(self) -> float:
        """
        Get CPU usage as percentage of the container's CPU limit.
        
        Reads cgroup usage_usec (v2) or cpuacct.usage (v1) and divides
        by the container's CPU limit (not the host's core count).
        
        Example: container with 100m limit using 100m = 100%.
        Previous bug: divided by os.cpu_count() (host cores, e.g. 64),
        so 100m usage on a 64-core host showed as 0.15% instead of 100%.
        """
        try:
            cpu_limit = self._get_cpu_limit_cores()

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
                
                # Calculate CPU percentage relative to container limit
                time_delta = current_time - self._last_cpu_time
                if time_delta > 0:
                    cpu_delta = (cpu_usec - self._last_cpu_usage) / 1_000_000
                    cpu_percent = (cpu_delta / time_delta / cpu_limit) * 100
                    
                    self._last_cpu_usage = cpu_usec
                    self._last_cpu_time = current_time
                    
                    return min(cpu_percent, 100.0)
            
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
                    cpu_percent = (cpu_delta / time_delta / cpu_limit) * 100
                    
                    self._last_cpu_usage = cpu_ns
                    self._last_cpu_time = current_time
                    
                    return min(cpu_percent, 100.0)
        
        except Exception as e:
            logger.debug(f"Cgroup CPU read failed, using psutil: {e}")
        
        # Fallback to psutil (non-blocking for smoother readings)
        return psutil.cpu_percent(interval=0.1)
    
    def _get_cgroup_memory_percent(self) -> float:
        """
        Get memory usage as a percentage of the container's memory limit.
        Reads from cgroup v2 (memory.current / memory.max) or
        cgroup v1 (memory.usage_in_bytes / memory.limit_in_bytes).
        Falls back to psutil if cgroup files are not available.
        """
        try:
            # cgroup v2
            usage_path_v2 = "/sys/fs/cgroup/memory.current"
            limit_path_v2 = "/sys/fs/cgroup/memory.max"

            if os.path.exists(usage_path_v2) and os.path.exists(limit_path_v2):
                with open(usage_path_v2, "r") as f:
                    usage = int(f.read().strip())
                with open(limit_path_v2, "r") as f:
                    limit_str = f.read().strip()
                    if limit_str == "max":
                        # No limit set, fallback to psutil
                        return psutil.virtual_memory().percent
                    limit = int(limit_str)
                
                if limit > 0:
                    return (usage / limit) * 100.0
                else:
                    return 0.0

            # cgroup v1
            usage_path_v1 = "/sys/fs/cgroup/memory/memory.usage_in_bytes"
            limit_path_v1 = "/sys/fs/cgroup/memory/memory.limit_in_bytes"

            if os.path.exists(usage_path_v1) and os.path.exists(limit_path_v1):
                with open(usage_path_v1, "r") as f:
                    usage = int(f.read().strip())
                with open(limit_path_v1, "r") as f:
                    limit = int(f.read().strip())

                # Check for ridiculously high limit values (effectively no limit)
                if limit > 2**60:
                    return psutil.virtual_memory().percent

                if limit > 0:
                    return (usage / limit) * 100.0
                else:
                    return 0.0

        except (IOError, ValueError, FileNotFoundError) as e:
            logger.debug(f"Cgroup memory read failed, using psutil: {e}")

        # Fallback to psutil
        return psutil.virtual_memory().percent

    def _collect_metrics(self) -> Metrics:
        """Collect current system metrics."""
        # Use cgroup stats for accurate container CPU (avoids psutil spikiness)
        cpu = self._get_cgroup_cpu_percent()
        memory = self._get_cgroup_memory_percent()
        error_rate = get_error_rate()
        
        return Metrics(
            cpu=cpu,
            memory=memory,
            error_rate=error_rate
        )
    
    # Env var suffixes that carry credentials or config, never hostnames.
    _NON_HOST_SUFFIXES = {"_USER", "_PASSWORD", "_PASS", "_NAME", "_PORT", "_SCHEMA", "_SSLMODE"}

    def _discover_topology(self) -> list[Dependency]:
        """
        Discover service dependencies by scanning environment variables.

        CRITICAL: Returns the env var KEY name (e.g., DATABASE_URL), not just the value.
        The SysAdmin Agent needs the key name to construct kubectl patch commands.

        Only env vars whose values look like hostnames or URLs are treated as
        dependency targets.  Credential / config keys (DB_USER, DB_PASSWORD,
        DB_NAME, DB_PORT …) are skipped to avoid ghost nodes in the topology.
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

            # Skip credential / config keys that never contain hostnames
            upper_key = key.upper()
            if any(upper_key.endswith(suffix) for suffix in self._NON_HOST_SUFFIXES):
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
            host = remainder.split("/")[0].split("@")[-1].split(":")[0]
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
            timeout=self.read_timeout
        )
        
        if response.status_code >= 400:
            logger.warning(f"Telemetry rejected: {response.status_code}")
        else:
            logger.debug(f"Telemetry sent: {payload.service}")
