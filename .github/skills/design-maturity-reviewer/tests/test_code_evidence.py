"""
Tests for search_code_evidence.py
"""

import unittest
from pathlib import Path

from scripts.git_context import resolve_git_context
from scripts.search_code_evidence import (
    extract_terms_from_text,
    hash_snippet,
    normalize_snippet,
    search_code_evidence,
)
from tests.helpers import TempGitRepo


class TestCodeEvidence(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = TempGitRepo()

    def tearDown(self) -> None:
        self.repo.cleanup()

    def test_extract_search_terms(self) -> None:
        text = "Validate 'Idempotency-Key' on /v1/settlements returning IDEMPOTENCY_CONCURRENT_REQUEST and calculated_fee_cents"
        terms = extract_terms_from_text(text)
        self.assertIn("Idempotency-Key", terms)
        self.assertIn("/v1/settlements", terms)
        self.assertIn("IDEMPOTENCY_CONCURRENT_REQUEST", terms)
        self.assertIn("calculated_fee_cents", terms)

    def test_search_committed_ref(self) -> None:
        settlement_code = (
            "import os\n\n"
            "def handle_settlement(request):\n"
            "    key = request.headers.get('Idempotency-Key')\n"
            "    if not key:\n"
            "        raise ValueError('Missing Idempotency-Key')\n"
            "    return {'status': 'OK'}\n"
        )
        self.repo.commit_file("src/settlement.py", settlement_code, "Add settlement handler")
        self.repo.push_to_origin("main")

        ctx = resolve_git_context(repo_root=self.repo.path, no_fetch=True)
        results = search_code_evidence(["Idempotency-Key"], ctx, ["src"])

        self.assertGreaterEqual(len(results), 1)
        res = results[0]
        self.assertEqual(res["file_path"], "src/settlement.py")
        self.assertIn("Idempotency-Key", res["snippet"])
        self.assertEqual(res["snippet_hash"], hash_snippet(res["snippet"]))

    def test_search_preview_working_tree(self) -> None:
        # Create uncommitted file in working tree
        uncommitted_code = (
            "def check_cache():\n"
            "    headers = {'X-Cache': 'HIT'}\n"
            "    return headers\n"
        )
        self.repo.create_file("src/cache.py", uncommitted_code)

        ctx = resolve_git_context(preview=True, repo_root=self.repo.path, no_fetch=True)
        results = search_code_evidence(["X-Cache"], ctx, ["src"])

        self.assertGreaterEqual(len(results), 1)
        res = results[0]
        self.assertEqual(res["file_path"], "src/cache.py")
        self.assertIn("X-Cache", res["snippet"])


if __name__ == "__main__":
    unittest.main()
