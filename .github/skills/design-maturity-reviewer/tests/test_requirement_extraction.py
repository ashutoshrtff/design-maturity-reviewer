"""
Tests for extract_requirements.py
"""

import json
import unittest
from pathlib import Path

from scripts.config_loader import find_repo_root
from scripts.extract_requirements import extract_from_design_chunks, map_ticket_scope


class TestRequirementExtraction(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = find_repo_root()
        chunks_file = self.repo_root / "knowledge-index" / "123456" / "chunks.json"
        with open(chunks_file, "r", encoding="utf-8") as f:
            self.chunks = json.load(f)

    def test_extract_from_chunks(self) -> None:
        reqs = extract_from_design_chunks(self.chunks, "123456", design_version=12)
        self.assertGreaterEqual(len(reqs), 5)
        self.assertTrue(all(r["requirement_id"].startswith("R-") for r in reqs))
        self.assertTrue(any(r["requirement_type"] == "validation" for r in reqs))
        # Verify ambiguous requirement flagged
        ambig = [r for r in reqs if "ambiguous" in r["flags"]]
        self.assertGreater(len(ambig), 0)

    def test_map_ticket_scope_and_no_design_basis(self) -> None:
        reqs = extract_from_design_chunks(self.chunks, "123456", design_version=12)
        ticket = {
            "key": "PAY-123",
            "summary": "Implement Idempotency for Settlement API",
            "description": "Additional Requirements: Export ledger to Excel spreadsheet (.xlsx)",
            "acceptance_criteria": [
                "Validate presence of Idempotency-Key header on POST /v1/settlements",
                "Return HTTP 409 Conflict with error code IDEMPOTENCY_CONCURRENT_REQUEST",
            ],
        }

        in_scope, outside_scope, no_db = map_ticket_scope(ticket, reqs)
        self.assertGreater(len(in_scope), 0)
        self.assertGreater(len(outside_scope), 0)
        self.assertIn("Export ledger to Excel spreadsheet (.xlsx)", no_db)


if __name__ == "__main__":
    unittest.main()
