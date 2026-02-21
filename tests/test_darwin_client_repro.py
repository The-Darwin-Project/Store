import sys
import os
import unittest
from unittest.mock import patch
from pathlib import Path

# Add src to sys.path
src_path = Path(__file__).resolve().parent.parent / "src"
sys.path.append(str(src_path))

from app.darwin_client import DarwinClient

class TestDarwinClient(unittest.TestCase):
    def test_discover_topology_excludes_db_user(self):
        client = DarwinClient(service="test-service", url="http://localhost:8000")
        
        # Mock environment variables
        env_vars = {
            "DB_USER": "postgres",
            "DB_PASSWORD": "password",
            "DATABASE_URL": "postgres://db-host:5432/db",
            "OTHER_SERVICE_HOST": "other-service"
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            dependencies = client._discover_topology()
            
            # Helper to get target names
            targets = [d.target for d in dependencies]
            env_vars_found = [d.env_var for d in dependencies]
            
            print(f"Found targets: {targets}")
            print(f"Found env vars: {env_vars_found}")
            
            # DATABASE_URL should be found
            self.assertIn("db-host", targets)
            
            # OTHER_SERVICE_HOST should be found
            self.assertIn("other-service", targets)
            
            # DB_USER should NOT be found (this is what we want to verify)
            self.assertNotIn("postgres", targets, "DB_USER='postgres' was incorrectly identified as a dependency target")
            self.assertNotIn("DB_USER", env_vars_found, "DB_USER was incorrectly identified as a dependency env var")

if __name__ == "__main__":
    unittest.main()
