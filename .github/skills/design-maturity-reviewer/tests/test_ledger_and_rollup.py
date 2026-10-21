"""
Tests for ledger.py and rollup.py
"""

import json
import unittest
from pathlib import Path

from scripts.ledger import get_latest_known_statuses, save_requirements, save_run_record
from scripts.rollup import process_rollup, render_coverage_markdown, revalidate_evidence_on_baseline
from scripts.search_code_evidence import hash_snippet
from tests.helpers import TempGitRepo


class TestLedgerAndRollup(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = TempGitRepo()

    def tearDown(self) -> None:
        self.repo.cleanup()

    def test_run_saving_and_ledger_status(self) -> None:
        run_data = {
            "jira_key": "PAY-123",
            "git_context": {"mode": "verified", "requested_ref": "origin/main", "resolved_commit": "abc12345"},
            "assessments": [
                {"requirement_id": "R-001", "status": "Implemented", "evidence": []},
                {"requirement_id": "R-002", "status": "Partial", "evidence": []},
            ],
        }

        save_run_record("123456", run_data, repo_root=self.repo.path)
        known = get_latest_known_statuses("123456", repo_root=self.repo.path)

        self.assertIn("R-001", known)
        self.assertEqual(known["R-001"]["status"], "Implemented")
        self.assertEqual(known["R-002"]["status"], "Partial")

    def test_rollup_promotes_squash_merge_and_handles_relocated_lines(self) -> None:
        # 1. Setup baseline requirements
        reqs = [
            {
                "requirement_id": "R-001",
                "requirement_text": "Idempotency validation on /v1/settlements",
                "source_citations": [{"heading_path": "Idempotency"}],
                "flags": [],
            }
        ]
        save_requirements("123456", reqs, repo_root=self.repo.path)

        # 2. Simulate refactor on main where code is at lines 10-14 (instead of original line 3)
        code_on_main = (
            "# License header\n"
            "# System imports\n"
            "import os\n"
            "import sys\n"
            "import time\n"
            "import logging\n\n"
            "# Handler implementation relocated down\n"
            "def validate_idempotency_key(header_val):\n"
            "    if not header_val:\n"
            "        raise ValueError('Invalid Idempotency-Key')\n"
            "    return True\n"
        )
        self.repo.commit_file("src/settlement.py", code_on_main, "Refactor settlement code into helper")
        self.repo.push_to_origin("main")

        snippet = (
            "def validate_idempotency_key(header_val):\n"
            "    if not header_val:\n"
            "        raise ValueError('Invalid Idempotency-Key')"
        )
        snip_hash = hash_snippet(snippet)

        # 3. Simulate an earlier ticket run that cited line 3 before the refactor
        earlier_run = {
            "jira_key": "PAY-123",
            "git_context": {"mode": "verified", "requested_ref": "origin/main", "resolved_commit": "old_sha"},
            "assessments": [
                {
                    "requirement_id": "R-001",
                    "status": "Implemented",
                    "evidence": [
                        {
                            "file_path": "src/settlement.py",
                            "line_number": 3,  # old line number
                            "snippet": snippet,
                            "snippet_hash": snip_hash,
                            "pr_number": 99,
                        }
                    ],
                }
            ],
        }
        save_run_record("123456", earlier_run, repo_root=self.repo.path)

        # 4. Run rollup
        rollup_res = process_rollup("123456", repo_root=self.repo.path, no_fetch=True)
        r001 = rollup_res["authoritative_results"]["R-001"]

        self.assertEqual(r001["status"], "Implemented")
        self.assertEqual(r001["evidence"][0]["line_number"], 9)  # relocated to line 9!
        self.assertIn("relocated from line 3", r001["evidence"][0]["revalidation_note"])
        self.assertEqual(rollup_res["counts"]["Implemented"], 1)
        self.assertEqual(rollup_res["coverage_percentage"], 100.0)

    def test_provisional_preview_evidence_excluded_from_baseline_counts(self) -> None:
        reqs = [
            {
                "requirement_id": "R-001",
                "requirement_text": "Feature on branch not yet merged",
                "source_citations": [{"heading_path": "Branch Feature"}],
                "flags": [],
            }
        ]
        save_requirements("123456", reqs, repo_root=self.repo.path)
        self.repo.push_to_origin("main")

        # Record a preview run where evidence is NOT present on origin/main
        preview_run = {
            "jira_key": "PAY-500",
            "git_context": {"mode": "preview", "requested_ref": "HEAD", "resolved_commit": "branch_sha"},
            "assessments": [
                {
                    "requirement_id": "R-001",
                    "status": "Implemented",
                    "evidence": [
                        {
                            "file_path": "src/unmerged.py",
                            "line_number": 5,
                            "snippet": "def unmerged_func(): pass",
                            "snippet_hash": "dummy_hash",
                            "pr_number": None,
                        }
                    ],
                }
            ],
        }
        save_run_record("123456", preview_run, repo_root=self.repo.path)

        rollup_res = process_rollup("123456", repo_root=self.repo.path, no_fetch=True)
        # Should be in provisional list, NOT counted as implemented in baseline
        self.assertEqual(rollup_res["counts"]["Implemented"], 0)
        self.assertEqual(len(rollup_res["provisional_items"]), 1)
        self.assertEqual(rollup_res["provisional_items"][0]["requirement_id"], "R-001")


if __name__ == "__main__":
    unittest.main()
