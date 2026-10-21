"""
Tests for preflight_index_check.py
"""

import unittest
from pathlib import Path

from scripts.config_loader import find_repo_root
from scripts.preflight_index_check import run_preflight


class TestPreflight(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = find_repo_root()

    def test_existing_page_passes(self) -> None:
        passed, res = run_preflight("123456", mode="ticket", repo_root=self.repo_root)
        self.assertTrue(passed)
        self.assertEqual(res["status"], "PASS")
        self.assertEqual(res["page_id"], "123456")
        self.assertGreater(res["chunk_count"], 0)

    def test_missing_page_fails_with_ingest_command(self) -> None:
        passed, res = run_preflight("999999", mode="ticket", repo_root=self.repo_root)
        self.assertFalse(passed)
        self.assertEqual(res["reason"], "MISSING_INDEX")
        self.assertIn("tools/knowledge-ingestion/ingest.py", res["message"])
        self.assertIn("999999", res["ingest_command"])


if __name__ == "__main__":
    unittest.main()
