"""
Generate sample ticket report (View 1) and baseline coverage report (View 2)
from fixtures and commit real settlement evidence to repo.
"""

import json
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

from scripts.assess_requirements import assess_requirements_list
from scripts.config_loader import find_repo_root
from scripts.extract_requirements import extract_from_design_chunks, map_ticket_scope
from scripts.fetch_jira_ticket import fetch_from_file
from scripts.find_pr_evidence import find_pr_evidence
from scripts.git_context import resolve_git_context
from scripts.ledger import save_requirements, save_run_record
from scripts.render_report import generate_ticket_report
from scripts.rollup import run_rollup
from scripts.validate_report import validate_assessment_report


def main() -> int:
    root = find_repo_root()

    # Load chunks
    chunks_file = root / "knowledge-index" / "123456" / "chunks.json"
    with open(chunks_file, "r", encoding="utf-8") as f:
        chunks = json.load(f)

    # Extract requirements
    reqs = extract_from_design_chunks(chunks, "123456", design_version=12)
    save_requirements("123456", reqs, repo_root=root)

    # Create sample application code in src/
    src_dir = root / "src"
    src_dir.mkdir(parents=True, exist_ok=True)
    pay_code = (
        'from fastapi import FastAPI, HTTPException, Request\n\n'
        'app = FastAPI()\n\n'
        '@app.post("/v1/settlements")\n'
        'def create_settlement(request: Request):\n'
        '    # Validate required Idempotency-Key header\n'
        '    idempotency_key = request.headers.get("Idempotency-Key")\n'
        '    if not idempotency_key:\n'
        '        raise HTTPException(status_code=400, detail="Missing required Idempotency-Key")\n\n'
        '    # Check cache for duplicate request\n'
        '    cached_response = check_idempotency_cache(idempotency_key)\n'
        '    if cached_response:\n'
        '        return {"status": "success", "cached": True, "headers": {"X-Cache": "HIT"}}\n\n'
        '    # Transaction fee calculation\n'
        '    fee_cents = calculate_tier_fee(request.amount_cents)\n'
        '    log_settlement_event("settlement_processed", calculated_fee_cents=fee_cents)\n\n'
        '    return {"status": "settled", "calculated_fee_cents": fee_cents}\n'
    )
    (src_dir / "settlement.py").write_text(pay_code, encoding="utf-8")

    # Add and commit to Git if changed
    subprocess.run(["git", "add", "src/settlement.py"], cwd=str(root), check=True)
    subprocess.run(
        ["git", "commit", "-m", "feat(settlement): implement settlement idempotency and fee calculation (#123)"],
        cwd=str(root),
        check=False,
    )

    ctx = resolve_git_context(repo_root=root, no_fetch=True)
    ticket_file = SKILL_DIR / "examples" / "fixtures" / "jira_PAY-123.json"
    ticket = fetch_from_file(ticket_file)

    in_scope, outside_scope, no_db = map_ticket_scope(ticket, reqs)
    assessments = assess_requirements_list(in_scope, ctx, search_paths=["src"])

    val_ok, errors = validate_assessment_report(assessments, ctx, chunks)
    if not val_ok:
        print(f"Validation failed: {errors}", file=sys.stderr)
        return 1

    pr_ev = find_pr_evidence("PAY-123", ctx)

    design_info = {
        "page_id": "123456",
        "page_title": "Instant Payment Settlement Engine",
        "page_version": 12,
        "ingested_at": "2026-10-21T00:00:00Z",
    }

    t_path, r_path = generate_ticket_report(
        ticket=ticket,
        design_info=design_info,
        git_context={
            "mode": ctx.mode,
            "requested_ref": ctx.requested_ref,
            "resolved_commit": ctx.resolved_commit,
            "current_branch": ctx.current_branch,
        },
        pr_evidence=pr_ev,
        in_scope_assessments=assessments,
        outside_scope_requirements=outside_scope,
        no_design_basis=no_db,
        repo_root=root,
    )

    cov_file = run_rollup("123456", repo_root=root, no_fetch=True)

    # Copy to examples directory
    examples_dir = SKILL_DIR / "examples"
    (examples_dir / "sample-PAY-123.md").write_text(t_path.read_text(encoding="utf-8"), encoding="utf-8")
    (examples_dir / "sample-COVERAGE.md").write_text(cov_file.read_text(encoding="utf-8"), encoding="utf-8")

    print(f"SUCCESS: Generated ticket report at {t_path}")
    print(f"SUCCESS: Generated baseline coverage report at {cov_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
