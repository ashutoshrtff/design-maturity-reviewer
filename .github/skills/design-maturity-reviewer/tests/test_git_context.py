"""
Tests for git_context.py
"""

import unittest
from pathlib import Path

from scripts.git_context import read_file_content, resolve_git_context
from tests.helpers import TempGitRepo


class TestGitContext(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = TempGitRepo()

    def tearDown(self) -> None:
        self.repo.cleanup()

    def test_default_baseline_resolution(self) -> None:
        # Commit a file on main and push to origin
        self.repo.commit_file("src/main.py", "print('hello main')\n", "Add main.py")
        self.repo.push_to_origin("main")

        ctx = resolve_git_context(repo_root=self.repo.path, no_fetch=True)
        self.assertIn("origin/main", ctx.base_ref)
        self.assertEqual(ctx.mode, "verified")
        self.assertFalse(ctx.is_dirty)

        # Read file at ref
        content = read_file_content("src/main.py", ctx)
        self.assertIsNotNone(content)
        self.assertIn("hello main", content)

    def test_preview_mode_uncommitted_changes(self) -> None:
        self.repo.commit_file("src/main.py", "print('committed')\n", "Initial commit")
        self.repo.push_to_origin("main")

        # Create untracked file
        self.repo.create_file("src/untracked.py", "print('untracked')\n")
        # Modify committed file without committing
        (self.repo.path / "src" / "main.py").write_text("print('modified in working tree')\n", encoding="utf-8")

        ctx = resolve_git_context(preview=True, repo_root=self.repo.path, no_fetch=True)
        self.assertEqual(ctx.mode, "preview")
        self.assertTrue(ctx.is_dirty)
        self.assertIn("src/untracked.py", ctx.untracked_files)

        # Reading file in preview mode should return working tree contents
        content = read_file_content("src/main.py", ctx)
        self.assertIn("modified in working tree", content)

        untracked_content = read_file_content("src/untracked.py", ctx)
        self.assertIn("untracked", untracked_content)


if __name__ == "__main__":
    unittest.main()
