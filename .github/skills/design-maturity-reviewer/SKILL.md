---
name: design-maturity-reviewer
description: Assess how much of a Confluence design a Jira ticket or pull request implements, evaluate design completeness across git refs, identify missing or partial requirements, and generate design maturity coverage reports.
---

# Design Maturity Reviewer (DMR)

The Design Maturity Reviewer evaluates implementation completeness against Confluence design requirements. It does not review code style or security; it verifies what is implemented, partial, pending, or unverifiable.

## Core Rules
1. **Evidence Determines Status**: Status comes exclusively from verified code at an explicit Git ref.
2. **Status vs Ownership**: Status = what code demonstrates. Ownership = which reviewed ticket claims the requirement. A requirement can be implemented without a reviewed ticket.
3. **PRs are for Attribution Only**: Never use PR existence or Jira "Done" status to decide implementation status.
4. **Never Invent Evidence**: Every `Implemented` requirement requires valid file, line, and snippet evidence. Unsupported claims must be rejected.
5. **Read-Only Codebase**: DMR never modifies application code. Outputs are written only under `design-status/<pageId>/`.

---

## Operating Modes

### Mode A: Ticket Review (`Jira Key` + `page_id`)
1. **Initialize & Check**:
   - Resolve config with `scripts/config_loader.py`.
   - Run `python scripts/doctor.py --page-id <page_id>`. If any check fails, stop and present fix hints.
   - Run `python scripts/preflight_index_check.py --page-id <page_id> --mode ticket`.
2. **Establish Git Reference**:
   - Default: `origin/main` (baseline).
   - If user asks to review local work, branch, or uncommitted changes, set `--preview`.
   - If PR number is provided, set `--pr <number>`.
3. **Fetch Ticket Scope**:
   - Run `python scripts/fetch_jira_ticket.py --key <JIRA-KEY>`.
   - Extract summary, description, and acceptance criteria.
4. **Retrieve Design Context & Extract Requirements**:
   - Run `python scripts/query_design_context.py --page-id <page_id> --query "<ticket summary and AC>"`.
   - If max relevance < min_relevance (default 0.35), issue a low-relevance warning.
   - Run `python scripts/extract_requirements.py` to identify in-scope requirements, outside-scope items, and items with no design basis.
5. **Search Evidence & Attribute**:
   - Run `python scripts/search_code_evidence.py` at the resolved ref for targeted terms.
   - Run `python scripts/find_pr_evidence.py` (3-level fallback) and `python scripts/attribute_evidence.py`.
6. **Assess & Validate**:
   - Run `python scripts/assess_requirements.py`.
   - Assign statuses: `Implemented`, `Partial`, `Pending`, `Unverifiable`.
   - Run `python scripts/validate_report.py`. Stop and fix if any validation fails.
7. **Record & Render**:
   - Save immutable run record in `design-status/<pageId>/runs/<run-id>.json`.
   - Render report to `design-status/<pageId>/tickets/<JIRA-KEY>.md`.
   - If preview mode, display the `PREVIEW (PROVISIONAL)` banner.

### Mode B: Design Baseline Coverage (`page_id` only)
1. **Initialize Baseline**:
   - Target ref is fixed to `origin/main`.
   - Run `python scripts/preflight_index_check.py --page-id <page_id> --mode baseline`. If behind main, require rebase before proceeding.
2. **Decompose Design Checklist**:
   - Extract all requirements across design chunks and save `design-status/<pageId>/requirements.json`.
3. **Inspect Repository & Re-verify**:
   - Re-verify only new, changed, Partial, Pending, or stale items.
   - Run `python scripts/assess_requirements.py` across the whole repository at `origin/main`.
   - Run `python scripts/validate_report.py`.
4. **Deterministic Rollup**:
   - Save baseline run record.
   - Run `python scripts/rollup.py --page-id <page_id>`.
   - Generates `design-status/<pageId>/COVERAGE.md`.

---

## Detailed References
- [Architecture & Execution Boundaries](references/architecture.md)
- [Status Definitions & Rules](references/status-definitions.md)
- [Requirement Extraction & Classification](references/requirement-extraction.md)
- [Evidence Rules & Valid Revalidation](references/evidence-rules.md)
- [Token & Performance Budget](references/token-budget.md)
- [Git References & Preview Semantics](references/git-refs.md)
- [Retrieval & Indexing](references/retrieval-and-indexing.md)
- [Security, Privacy & Subprocess Safety](references/security-and-privacy.md)
- [Report Contract Specifications](references/report-contract.md)
- [Extension Points & Roadmap](references/extension-points.md)
