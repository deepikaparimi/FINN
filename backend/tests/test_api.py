import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.main import app


class FixtureApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = str(Path(self.temp_dir.name) / "finn.sqlite3")
        self.database_patch = patch.dict(os.environ, {"DATABASE_PATH": self.database_path, "FINN_OFFLINE": "1"})
        self.database_patch.start()
        self.client = TestClient(app)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.database_patch.stop()
        self.temp_dir.cleanup()

    def test_health(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_digest_uses_fixture_announcements(self):
        response = self.client.get("/api/digest?hours=336")
        self.assertEqual(response.status_code, 200)
        self.assertIn("announcements", response.json())
        self.assertTrue(any(item["source"] == "sample" for item in response.json()["announcements"]))

    def test_alerts_use_fixture_prices(self):
        response = self.client.get("/api/alerts")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIsNotNone(payload["as_of"])
        self.assertIn("alerts", payload)

    def test_research_uses_reliance_fixture(self):
        response = self.client.get("/api/research/RELIANCE")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["found"])
        self.assertEqual(payload["ticker"], "RELIANCE")
        self.assertIn("metrics", payload)


if __name__ == "__main__":
    unittest.main()
