"""
Tests for find_pr_evidence.py
"""

import unittest
from pathlib import Path

from scripts.find_pr_evidence import find_pr_evidence
from scripts.git_context import resolve_git_context
from tests.helpers import TempGitRepo


class TestPrEvidence(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = TempGitRepo()

    def tearDown(self) -> None:
        self.repo.cleanup()

    def test_level_2_git_history_fallback(self) -> None:
        # Commit with PR message format: "PAY-123 implement idempotency (#142)"
        self.repo.commit_file("src/pay.py", "x = 1\n", "PAY-123 implement idempotency (#142)")
        self.repo.push_to_origin("main")

        ctx = resolve_git_context(repo_root=self.repo.path, no_fetch=True)
        res = find_pr_evidence("PAY-123", ctx)

        self.assertEqual(res["level"], 2)
        self.assertEqual(res["attribution_method"], "git_history")
        self.assertEqual(res["pr_number"], 142)
        self.assertIn("Inferred from git commit message", res["attribution_limitations"])

    def test_level_3_branch_changes_fallback(self) -> None:
        # Commit baseline on main
        self.repo.push_to_origin("main")

        # Create new branch with local commit mentioning PAY-123 but without PR #
        self.repo.run_git("checkout", "-b", "feature/PAY-123")
        self.repo.commit_file("src/local.py", "y = 2\n", "WIP on PAY-123")

        ctx = resolve_git_context(preview=True, repo_root=self.repo.path, no_fetch=True)
        # Search for a ticket key that has no PR #
        res = find_pr_evidence("PAY-999", ctx)

        self.assertEqual(res["level"], 3)
        self.assertEqual(res["attribution_method"], "branch_changes")
        self.assertIsNone(res["pr_number"])
        self.assertIn("No PR found", res["attribution_limitations"])


if __name__ == "__main__":
    unittest.main()
