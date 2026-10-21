"""
End-to-end acceptance test for Design Maturity Reviewer.
Demonstrates full offline workflow from ticket preview to squash merge and deterministic rollup.
"""

import json
import unittest
from pathlib import Path

from scripts.assess_requirements import assess_requirements_list
from scripts.config_loader import find_repo_root
from scripts.extract_requirements import extract_from_design_chunks, map_ticket_scope
from scripts.fetch_jira_ticket import fetch_from_file
from scripts.find_pr_evidence import find_pr_evidence
from scripts.git_context import resolve_git_context
from scripts.ledger import save_requirements, save_run_record
from scripts.preflight_index_check import run_preflight
from scripts.query_design_context import query_design_context
from scripts.render_report import generate_ticket_report
from scripts.rollup import process_rollup, run_rollup
from scripts.validate_report import validate_assessment_report
from tests.helpers import TempGitRepo


class TestEndToEndFlow(unittest.TestCase):
    def setUp(self) -> None:
        self.workspace_root = find_repo_root()
        self.repo = TempGitRepo()

        # Ingested chunks from knowledge-index
        chunks_file = self.workspace_root / "knowledge-index" / "123456" / "chunks.json"
        with open(chunks_file, "r", encoding="utf-8") as f:
            self.chunks = json.load(f)

        # Jira fixture
        jira_file = (
            self.workspace_root
            / ".github"
            / "skills"
            / "design-maturity-reviewer"
            / "examples"
            / "fixtures"
            / "jira_PAY-123.json"
        )
        self.ticket = fetch_from_file(jira_file)

    def tearDown(self) -> None:
        self.repo.cleanup()

    def test_complete_e2e_ticket_preview_squash_and_rollup(self) -> None:
        # Step 1: Preflight check on knowledge-index
        passed, preflight_res = run_preflight(
            "123456", mode="ticket", repo_root=self.workspace_root, no_fetch=True
        )
        self.assertTrue(passed)

        # Step 2: Extract requirements from design chunks and save baseline checklist
        reqs = extract_from_design_chunks(self.chunks, "123456", design_version=12)
        save_requirements("123456", reqs, repo_root=self.repo.path)
        self.assertGreaterEqual(len(reqs), 5)

        # Step 3: Developer works on feature branch with uncommitted changes (PREVIEW mode)
        self.repo.run_git("checkout", "-b", "feature/PAY-123")
        payment_code = (
            "from fastapi import HTTPException, Request\n\n"
            "@app.post('/v1/settlements')\n"
            "def handle_settlement(req: Request):\n"
            "    # Validate Idempotency-Key header\n"
            "    key = req.headers.get('Idempotency-Key')\n"
            "    if not key:\n"
            "        raise HTTPException(status_code=400, detail='Missing Idempotency-Key')\n"
            "    # Check duplicate cache\n"
            "    return {'status': 'processed', 'headers': {'X-Cache': 'HIT'}}\n"
        )
        self.repo.create_file("src/settlement.py", payment_code)

        preview_ctx = resolve_git_context(preview=True, repo_root=self.repo.path, no_fetch=True)
        self.assertEqual(preview_ctx.mode, "preview")

        # Step 4: Map ticket scope and assess in preview mode
        in_scope, outside_scope, no_db = map_ticket_scope(self.ticket, reqs)
        self.assertGreater(len(in_scope), 0)

        assessments = assess_requirements_list(in_scope, preview_ctx, search_paths=["src"])

        # Step 5: Anti-hallucination validation
        val_passed, errors = validate_assessment_report(assessments, preview_ctx, self.chunks)
        self.assertTrue(val_passed, f"Validation errors: {errors}")

        # Step 6: Find PR evidence (Level 3 branch diff fallback)
        pr_ev = find_pr_evidence("PAY-123", preview_ctx)
        self.assertEqual(pr_ev["level"], 3)

        # Step 7: Render ticket report
        design_info = {
            "page_id": "123456",
            "page_title": "Instant Payment Settlement Engine",
            "page_version": 12,
            "ingested_at": "2026-10-21T00:00:00Z",
        }
        report_path, run_path = generate_ticket_report(
            ticket=self.ticket,
            design_info=design_info,
            git_context={
                "mode": preview_ctx.mode,
                "requested_ref": preview_ctx.requested_ref,
                "resolved_commit": preview_ctx.resolved_commit,
                "current_branch": preview_ctx.current_branch,
            },
            pr_evidence=pr_ev,
            in_scope_assessments=assessments,
            outside_scope_requirements=outside_scope,
            no_design_basis=no_db,
            repo_root=self.repo.path,
        )
        self.assertTrue(report_path.exists())
        self.assertTrue(run_path.exists())

        report_content = report_path.read_text(encoding="utf-8")
        self.assertIn("PREVIEW (PROVISIONAL) RUN", report_content)

        # Step 8: Run rollup before merge -> preview evidence must be quarantined under Provisional
        rollup_pre = process_rollup("123456", repo_root=self.repo.path, no_fetch=True)
        self.assertEqual(rollup_pre["counts"]["Implemented"], 0)
        self.assertGreater(len(rollup_pre["provisional_items"]), 0)

        # Step 9: Simulate PR squash merge into origin/main
        self.repo.run_git("checkout", "main")
        # In a squash merge, commit message includes (#123) and commit SHA is new
        self.repo.commit_file(
            "src/settlement.py",
            payment_code,
            "feat(settlement): implement idempotency validation (#123)",
        )
        self.repo.push_to_origin("main")

        # Step 10: Run deterministic rollup again on origin/main baseline
        rollup_post = process_rollup("123456", repo_root=self.repo.path, no_fetch=True)

        # Code is now on origin/main -> content revalidation promotes it!
        self.assertGreater(rollup_post["counts"]["Implemented"], 0)
        self.assertEqual(len(rollup_post["provisional_items"]), 0)

        # Generate COVERAGE.md file
        cov_file = run_rollup("123456", repo_root=self.repo.path, no_fetch=True)
        self.assertTrue(cov_file.exists())
        cov_text = cov_file.read_text(encoding="utf-8")
        self.assertIn("Headline Implemented Coverage", cov_text)
        self.assertIn("Baseline Requirements Ledger", cov_text)


if __name__ == "__main__":
    unittest.main()
