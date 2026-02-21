# Store/tests/conftest.py
# @ai-rules:
# 1. [Pattern]: Centralizes sys.path setup so individual test files don't need it.
# 2. [Constraint]: No test fixtures defined here yet -- add as needed.
# 3. [Gotcha]: Must be in tests/ root for pytest auto-discovery.

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
