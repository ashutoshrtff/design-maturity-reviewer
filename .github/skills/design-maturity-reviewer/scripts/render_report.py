"""
Report renderer for DMR.
Generates Output View 1 (Coverage per Jira ticket) and View 2 (Coverage per Confluence design).
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from config_loader import find_repo_root
from ledger import get_latest_known_statuses, get_status_dir, save_run_record


def render_ticket_report_markdown(
    ticket: Dict[str, Any],
    design_info: Dict[str, Any],
    git_context: Dict[str, Any],
    pr_evidence: Dict[str, Any],
    in_scope_assessments: List[Dict[str, Any]],
    outside_scope_items: List[Dict[str, Any]],
    no_design_basis: List[str],
    low_relevance_warning: bool = False,
    stale_warning: Optional[str] = None,
    run_id: str = "",
) -> str:
    jira_key = ticket.get("key", "TICKET")
    summary = ticket.get("summary", "")
    page_id = design_info.get("page_id", "")
    page_title = design_info.get("page_title", "")
    page_version = design_info.get("page_version", 1)
    index_date = design_info.get("ingested_at", "")
    mode = git_context.get("mode", "verified")
    ref = git_context.get("requested_ref", "")
    commit = (git_context.get("resolved_commit", "") or "")[:8]

    # Calculate status counts
    counts = {"Implemented": 0, "Partial": 0, "Pending": 0, "Unverifiable": 0, "Not yet assessed": 0}
    for a in in_scope_assessments:
        st = a.get("status", "Not yet assessed")
        counts[st] = counts.get(st, 0) + 1

    total_in_scope = len(in_scope_assessments)
    verdict = (
        f"**Verdict**: Ticket implements {counts['Implemented']} of {total_in_scope} in-scope requirements."
        if counts["Implemented"] == total_in_scope
        else f"**Verdict**: Incomplete. {counts['Implemented']} implemented, {counts['Partial']} partial, {counts['Pending']} pending."
    )

    lines: List[str] = []

    # PREVIEW Banner
    if mode == "preview":
        lines.extend([
            "> [!IMPORTANT]",
            f"> **PREVIEW (PROVISIONAL) RUN**: Reviewing working tree on branch `{git_context.get('current_branch')}` ({commit}).",
            "> Results are provisional and become official once PR is merged to `origin/main` and rollup runs.",
            "",
        ])

    lines.extend([
        f"# Design Maturity Review: {jira_key}",
        f"**Summary**: {summary}  ",
        f"**Design Page**: [{page_title} (ID: {page_id})](#) · **Version**: {page_version} · **Indexed**: {index_date}  ",
        f"**Code Reference**: `{ref}` (`{commit}`) · **Mode**: `{mode.upper()}`  ",
        f"**PR Attribution**: PR #{pr_evidence.get('pr_number') or 'None'} (`{pr_evidence.get('attribution_method')}`) — {pr_evidence.get('attribution_limitations', '')}  ",
        f"**Run ID**: `{run_id}`  ",
        "",
        "## Maturity Status Summary",
        f"- **Implemented**: {counts['Implemented']}",
        f"- **Partial**: {counts['Partial']}",
        f"- **Pending**: {counts['Pending']}",
        f"- **Unverifiable**: {counts['Unverifiable']}",
        f"- **Total In-Scope Requirements**: {total_in_scope}",
        "",
        verdict,
        "",
    ])

    if low_relevance_warning:
        lines.extend([
            "> [!WARNING]",
            "> **Low Relevance Warning**: Design context retrieval scores for this ticket were weak overall.",
            f"> Please confirm whether ticket {jira_key} actually belongs to Confluence page {page_id}.",
            "",
        ])

    if stale_warning:
        lines.extend([
            "> [!WARNING]",
            f"> {stale_warning}",
            "",
        ])

    # Table of in-scope requirements
    lines.extend([
        "---",
        "",
        "## In-Scope Requirements Assessment",
        "",
        "| ID | Requirement | Status | Delivering PR/Commit | Design Section | Evidence |",
        "|---|---|---|---|---|---|",
    ])

    for a in in_scope_assessments:
        req_id = a.get("requirement_id", "")
        req_text = a.get("requirement_text", "").replace("|", "\\|")
        if len(req_text) > 65:
            req_text = req_text[:62] + "..."
        status = a.get("status", "")
        pr_or_commit = "-"
        ev_str = "-"
        if a.get("evidence"):
            e0 = a["evidence"][0]
            pr_or_commit = e0.get("pr_number") or e0.get("commit_sha") or "-"
            ev_str = f"`{e0.get('file_path')}:{e0.get('line_number')}`"
        heading = a.get("source_citations", [{}])[0].get("heading_path", "Design Section").replace("|", "\\|")
        lines.append(f"| {req_id} | {req_text} | **{status}** | {pr_or_commit} | {heading} | {ev_str} |")

    # Partial & Pending Details
    gaps = [a for a in in_scope_assessments if a.get("status") in ("Partial", "Pending")]
    if gaps:
        lines.extend([
            "",
            "---",
            "",
            "## Incomplete Implementation Details & Next Steps",
            "",
        ])
        for g in gaps:
            req_id = g.get("requirement_id")
            lines.append(f"### {req_id}: {g.get('requirement_text')}")
            lines.append(f"- **Status**: `{g.get('status')}`")
            lines.append(f"- **Assessment Rationale**: {g.get('rationale')}")
            if g.get("missing_criteria"):
                lines.append(f"- **Missing Criteria**: {'; '.join(g.get('missing_criteria'))}")
            lines.append("")

    # Ticket Items with No Design Basis
    if no_design_basis:
        lines.extend([
            "---",
            "",
            "## Ticket Items with No Design Basis",
            "> [!NOTE]",
            "> The following items in this Jira ticket have no matching requirements on this Confluence design page (possible scope creep or outdated design doc):",
            "",
        ])
        for item in no_design_basis:
            lines.append(f"- `{item}`")
        lines.append("")

    # Outside this ticket's scope
    if outside_scope_items:
        lines.extend([
            "---",
            "",
            "## Outside This Ticket's Scope (Informational Only)",
            "_These requirements belong to the design page but are outside this ticket's scope. Statuses are the latest known from previous runs and are not re-verified during this ticket review._",
            "",
            "| ID | Requirement | Latest Known Status | Source Run |",
            "|---|---|---|---|",
        ])
        for o in outside_scope_items:
            req_id = o.get("requirement_id")
            req_text = o.get("requirement_text", "").replace("|", "\\|")
            if len(req_text) > 70:
                req_text = req_text[:67] + "..."
            latest_st = o.get("latest_status", "Not yet assessed")
            source_run = o.get("source_run_id", "Ledger")
            lines.append(f"| {req_id} | {req_text} | {latest_st} | `{source_run}` |")
        lines.append("")

    # Unverifiable & Ambiguity Notes
    unverifiable = [a for a in in_scope_assessments if a.get("status") == "Unverifiable" or "ambiguous" in a.get("flags", [])]
    if unverifiable:
        lines.extend([
            "---",
            "",
            "## Unverifiable & Ambiguity Notes",
            "",
        ])
        for u in unverifiable:
            lines.append(f"### {u.get('requirement_id')}: {u.get('requirement_text')}")
            lines.append(f"- **Flags**: `{', '.join(u.get('flags', []))}`")
            lines.append(f"- **Rationale**: {u.get('rationale')}")
            if u.get("human_verification_needed"):
                lines.append(f"- **Human Verification Action**: {u.get('human_verification_needed')}")
            lines.append("")

    return "\n".join(lines) + "\n"


def generate_ticket_report(
    ticket: Dict[str, Any],
    design_info: Dict[str, Any],
    git_context: Dict[str, Any],
    pr_evidence: Dict[str, Any],
    in_scope_assessments: List[Dict[str, Any]],
    outside_scope_requirements: List[Dict[str, Any]],
    no_design_basis: List[str],
    low_relevance_warning: bool = False,
    stale_warning: Optional[str] = None,
    repo_root: Optional[Path] = None,
) -> Tuple[Path, Path]:
    root = repo_root or find_repo_root()
    page_id = str(design_info.get("page_id", "123456"))
    status_dir = get_status_dir(page_id, root)
    jira_key = ticket.get("key", "TICKET")

    # Get latest known statuses for outside scope
    known = get_latest_known_statuses(page_id, root)
    outside_enriched = []
    for o in outside_scope_requirements:
        r_id = o.get("requirement_id")
        k_info = known.get(r_id, {})
        outside_enriched.append({
            "requirement_id": r_id,
            "requirement_text": o.get("requirement_text", ""),
            "latest_status": k_info.get("status", "Not yet assessed"),
            "source_run_id": k_info.get("run_id", "Ledger baseline"),
        })

    # Prepare run record
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    run_data = {
        "jira_key": jira_key,
        "design_id": page_id,
        "design_version": design_info.get("page_version", 1),
        "timestamp": now_iso,
        "git_context": git_context,
        "pr_evidence": pr_evidence,
        "assessments": in_scope_assessments,
        "no_design_basis": no_design_basis,
        "low_relevance_warning": low_relevance_warning,
    }

    run_file = save_run_record(page_id, run_data, root)
    run_id = run_data["run_id"]

    # Render Markdown report
    md = render_ticket_report_markdown(
        ticket=ticket,
        design_info=design_info,
        git_context=git_context,
        pr_evidence=pr_evidence,
        in_scope_assessments=in_scope_assessments,
        outside_scope_items=outside_enriched,
        no_design_basis=no_design_basis,
        low_relevance_warning=low_relevance_warning,
        stale_warning=stale_warning,
        run_id=run_id,
    )

    ticket_report_path = status_dir / "tickets" / f"{jira_key}.md"
    ticket_report_path.write_text(md, encoding="utf-8")

    return ticket_report_path, run_file


def main() -> int:
    parser = argparse.ArgumentParser(description="Render ticket report.")
    parser.add_argument("--run-file", required=True, help="Path to run file JSON")
    args = parser.parse_args()

    with open(args.run_file, "r", encoding="utf-8") as f:
        run_data = json.load(f)

    # Simple CLI echo
    print(f"Loaded run {run_data.get('run_id')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
