"""
Tests for attribute_evidence.py
"""

import unittest
from pathlib import Path

from scripts.attribute_evidence import attribute_line
from scripts.git_context import resolve_git_context
from tests.helpers import TempGitRepo


class TestAttributeEvidence(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = TempGitRepo()

    def tearDown(self) -> None:
        self.repo.cleanup()

    def test_attribute_committed_line(self) -> None:
        sha = self.repo.commit_file("src/pay.py", "idempotency_key = True\n", "PAY-123 add key (#88)")
        self.repo.push_to_origin("main")

        ctx = resolve_git_context(repo_root=self.repo.path, no_fetch=True)
        attr = attribute_line("src/pay.py", 1, ctx)

        self.assertEqual(attr["file_path"], "src/pay.py")
        self.assertEqual(attr["line_number"], 1)
        self.assertEqual(attr["commit_sha"], sha[:8])
        self.assertEqual(attr["pr_number"], 88)
        self.assertEqual(attr["attribution_source"], "git_blame")

    def test_attribute_preview_uncommitted_line(self) -> None:
        self.repo.create_file("src/new_feature.py", "uncommitted_code = 123\n")

        ctx = resolve_git_context(preview=True, repo_root=self.repo.path, no_fetch=True)
        attr = attribute_line("src/new_feature.py", 1, ctx)

        self.assertIn("working_tree", attr["attribution_source"])
        self.assertEqual(attr["confidence"], "provisional")


if __name__ == "__main__":
    unittest.main()
