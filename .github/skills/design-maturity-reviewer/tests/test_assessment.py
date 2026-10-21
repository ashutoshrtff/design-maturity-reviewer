"""
Tests for assess_requirements.py
"""

import unittest
from pathlib import Path

from scripts.assess_requirements import evaluate_requirement
from scripts.git_context import resolve_git_context
from tests.helpers import TempGitRepo


class TestAssessRequirements(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = TempGitRepo()

    def tearDown(self) -> None:
        self.repo.cleanup()

    def test_implemented_status(self) -> None:
        code = (
            "def handle_settlement(req):\n"
            "    key = req.headers.get('Idempotency-Key')\n"
            "    if not key:\n"
            "        raise ValueError('Missing Idempotency-Key')\n"
            "    return {'status': 'processed'}\n"
        )
        self.repo.commit_file("src/settlement.py", code, "Add settlement")
        self.repo.push_to_origin("main")

        ctx = resolve_git_context(repo_root=self.repo.path, no_fetch=True)
        req = {
            "requirement_id": "R-002",
            "requirement_text": "All incoming payment settlement requests must validate 'Idempotency-Key'",
            "acceptance_criteria": ["Validate presence of 'Idempotency-Key' header on incoming settlement requests"],
            "flags": [],
        }

        res = evaluate_requirement(req, ctx, search_paths=["src"])
        self.assertEqual(res["status"], "Implemented")
        self.assertGreater(len(res["evidence"]), 0)

    def test_partial_status(self) -> None:
        # Code validates key but does NOT return IDEMPOTENCY_CONCURRENT_REQUEST
        code = (
            "def handle_settlement(req):\n"
            "    key = req.headers.get('Idempotency-Key')\n"
            "    return {'status': 'OK'}\n"
        )
        self.repo.commit_file("src/settlement.py", code, "Add partial settlement")
        self.repo.push_to_origin("main")

        ctx = resolve_git_context(repo_root=self.repo.path, no_fetch=True)
        req = {
            "requirement_id": "R-003",
            "requirement_text": "The engine must check if key was processed and handle concurrency",
            "acceptance_criteria": [
                "Validate presence of 'Idempotency-Key'",
                "Return HTTP 409 Conflict with code IDEMPOTENCY_CONCURRENT_REQUEST if concurrent",
            ],
            "flags": [],
        }

        res = evaluate_requirement(req, ctx, search_paths=["src"])
        self.assertEqual(res["status"], "Partial")
        self.assertIn("IDEMPOTENCY_CONCURRENT_REQUEST", res["missing_criteria"][0])

    def test_pending_status(self) -> None:
        self.repo.push_to_origin("main")
        ctx = resolve_git_context(repo_root=self.repo.path, no_fetch=True)

        req = {
            "requirement_id": "R-007",
            "requirement_text": "Settlement audit records must be uploaded to AWS S3 bucket 'settlement-audit-archive'",
            "acceptance_criteria": ["Upload compressed records to 'settlement-audit-archive'"],
            "flags": [],
        }

        res = evaluate_requirement(req, ctx, search_paths=["src"])
        self.assertEqual(res["status"], "Pending")
        self.assertEqual(len(res["evidence"]), 0)

    def test_unverifiable_infrastructure(self) -> None:
        ctx = resolve_git_context(repo_root=self.repo.path, no_fetch=True)
        req = {
            "requirement_id": "R-006",
            "requirement_text": "Database failover must switch to secondary replica across AWS Availability Zones in under 500ms without data loss",
            "acceptance_criteria": ["Failover multi-AZ under 500ms"],
            "flags": [],
        }

        res = evaluate_requirement(req, ctx, search_paths=["src"])
        self.assertEqual(res["status"], "Unverifiable")
        self.assertIsNotNone(res["human_verification_needed"])


if __name__ == "__main__":
    unittest.main()
