"""
Tests for query_design_context.py
"""

import unittest
from pathlib import Path

from scripts.config_loader import find_repo_root
from scripts.query_design_context import query_design_context


class TestFaissQuery(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = find_repo_root()
        self.index_dir = self.repo_root / "knowledge-index"

    def test_query_schema_and_relevance(self) -> None:
        res = query_design_context(
            query="Idempotency-Key header on /v1/settlements",
            page_id="123456",
            index_base_dir=self.index_dir,
            top_k=4,
            min_relevance=0.35,
        )
        self.assertEqual(res["page_id"], "123456")
        self.assertIn("chunks", res)
        self.assertLessEqual(len(res["chunks"]), 4)
        self.assertGreater(res["max_relevance"], 0.35)
        self.assertFalse(res["low_relevance_warning"])

        top_chunk = res["chunks"][0]
        self.assertIn("Idempotency", top_chunk["heading_path"])
        self.assertIn("score", top_chunk)

    def test_low_relevance_warning_on_unrelated_query(self) -> None:
        res = query_design_context(
            query="Fix Android biometric touch ID timeout animation",
            page_id="123456",
            index_base_dir=self.index_dir,
            top_k=4,
            min_relevance=0.35,
        )
        self.assertTrue(res["low_relevance_warning"])


if __name__ == "__main__":
    unittest.main()
