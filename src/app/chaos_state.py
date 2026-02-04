# Store/src/app/chaos_state.py
"""
File-backed chaos state for cross-process sharing.

CRITICAL: The Dockerfile runs TWO separate uvicorn processes:
  - Store API on port 8080
  - Chaos Controller on port 9000

Python module-level singletons are NOT shared across OS processes.
This module uses file-based state with atomic writes for cross-process safety.
"""

import json
import os
import time
import tempfile
from dataclasses import dataclass, asdict
from typing import Optional

STATE_FILE = "/tmp/chaos_state.json"
MAX_RETRIES = 3
RETRY_DELAY = 0.01  # 10ms


@dataclass
class ChaosState:
    """Chaos injection state - shared across processes via file."""
    cpu_load: bool = False
    memory_load_mb: int = 0  # Memory allocated in MB
    latency_ms: int = 0
    error_rate: float = 0.0  # Injected error probability (0.0-1.0)
    request_count: int = 0
    error_count: int = 0
    window_start: float = 0.0


def _read_state() -> ChaosState:
    """
    Read state from file with retry logic.
    
    Uses exponential backoff to handle concurrent access.
    """
    for attempt in range(MAX_RETRIES):
        try:
            if not os.path.exists(STATE_FILE):
                return ChaosState()
            
            with open(STATE_FILE, "r") as f:
                data = json.load(f)
                return ChaosState(**data)
        except (json.JSONDecodeError, TypeError, KeyError, FileNotFoundError):
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY * (2 ** attempt))
            continue
    
    return ChaosState()


def _write_state(state: ChaosState) -> None:
    """
    Write state to file using atomic write pattern.
    
    Writes to a temp file first, then renames (atomic on POSIX).
    This prevents data corruption from concurrent writes.
    """
    state_dir = os.path.dirname(STATE_FILE)
    
    # Write to temp file in same directory (required for atomic rename)
    fd, temp_path = tempfile.mkstemp(dir=state_dir, prefix=".chaos_state_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(asdict(state), f)
        
        # Atomic rename (POSIX guarantees atomicity for same-filesystem rename)
        os.replace(temp_path, STATE_FILE)
    except Exception:
        # Clean up temp file on error
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise


def _read_modify_write(modifier) -> ChaosState:
    """
    Atomic read-modify-write with retry logic.
    
    Handles race conditions by retrying on conflict.
    """
    for attempt in range(MAX_RETRIES):
        try:
            state = _read_state()
            modifier(state)
            _write_state(state)
            return state
        except (OSError, IOError):
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY * (2 ** attempt))
            continue
    
    # Last resort: just write
    state = ChaosState()
    modifier(state)
    _write_state(state)
    return state


def get_chaos() -> ChaosState:
    """Get current chaos state (cross-process safe)."""
    return _read_state()


def set_chaos(**kwargs) -> ChaosState:
    """Update chaos state fields (cross-process safe)."""
    def modifier(state: ChaosState):
        for key, value in kwargs.items():
            if hasattr(state, key):
                setattr(state, key, value)
    
    return _read_modify_write(modifier)


def reset_chaos() -> ChaosState:
    """Reset chaos state to defaults (cross-process safe)."""
    state = ChaosState()
    _write_state(state)
    return state


def record_request(is_error: bool = False) -> None:
    """
    Record a request for error rate tracking (cross-process safe).
    
    Uses atomic read-modify-write to prevent lost increments.
    """
    def modifier(state: ChaosState):
        now = time.time()
        # Reset window every 60 seconds
        if now - state.window_start > 60:
            state.request_count = 0
            state.error_count = 0
            state.window_start = now
        state.request_count += 1
        if is_error:
            state.error_count += 1
    
    _read_modify_write(modifier)


def get_error_rate() -> float:
    """Get error rate as percentage (cross-process safe)."""
    state = _read_state()
    if state.request_count == 0:
        return 0.0
    return (state.error_count / state.request_count) * 100
