"""
Deterministic rollup engine for Design Maturity Reviewer.
Aggregates run files, revalidates code evidence against origin/main via hash matching,
partitions provisional preview evidence, resolves run disagreements, and generates COVERAGE.md.
No LLM calls are used during rollup.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from config_loader import find_repo_root, load_config
from git_context import GitContext, get_commit_sha, read_file_content, resolve_git_context, run_git_cmd
from ledger import get_status_dir, list_run_records, load_requirements
from search_code_evidence import hash_snippet, normalize_snippet


def revalidate_evidence_on_baseline(
    ev: Dict[str, Any], baseline_context: GitContext, repo_root: Path
) -> Tuple[bool, int, str]:
    """
    Check if the evidence snippet exists at origin/main (baseline).
    Returns (is_valid, current_line_number, reason).
    Handles line movement / refactoring by scanning the file for the normalized snippet.
    """
    file_path = ev.get("file_path", "")
    content = read_file_content(file_path, baseline_context)
    if content is None:
        return False, 0, f"File {file_path} not found at {baseline_context.requested_ref}"

    lines = content.splitlines()
    target_snip = ev.get("snippet", "")
    target_hash = ev.get("snippet_hash") or hash_snippet(target_snip)
    norm_target = normalize_snippet(target_snip)

    # 1. Try cited line number first
    cited_line = ev.get("line_number", 1)
    if 1 <= cited_line <= len(lines):
        start_l = max(0, cited_line - 4)
        end_l = min(len(lines), cited_line + 4)
        local_chunk = normalize_snippet("\n".join(lines[start_l:end_l]))
        if norm_target in local_chunk:
            return True, cited_line, "Exact line match on baseline"

    # 2. If moved, scan file for the multi-line snippet
    target_lines = norm_target.splitlines()
    target_len = len(target_lines)
    for i in range(len(lines) - target_len + 1):
        window = normalize_snippet("\n".join(lines[i : i + target_len]))
        if window == norm_target:
            return True, i + 1, f"Snippet moved: relocated from line {cited_line} to line {i + 1}"

    # 3. Check wider sliding window
    for i in range(len(lines)):
        end_idx = min(len(lines), i + max(6, target_len + 2))
        window = normalize_snippet("\n".join(lines[i:end_idx]))
        if norm_target in window:
            return True, i + 1, f"Snippet moved: relocated from line {cited_line} to line {i + 1}"

    return False, 0, "Snippet not present at baseline reference"


def process_rollup(
    page_id: str,
    baseline_ref: str = "origin/main",
    repo_root: Optional[Path] = None,
    no_fetch: bool = True,
) -> Dict[str, Any]:
    root = repo_root or find_repo_root()
    baseline_ctx = resolve_git_context(requested_ref=baseline_ref, no_fetch=no_fetch, repo_root=root)
    status_dir = get_status_dir(page_id, root)

    all_reqs = load_requirements(page_id, root)
    req_map = {r["requirement_id"]: r for r in all_reqs}
    all_runs = list_run_records(page_id, root)

    # Group assessments by requirement_id
    req_runs: Dict[str, List[Dict[str, Any]]] = {}
    for run in all_runs:
        run_mode = run.get("git_context", {}).get("mode", "verified")
        run_ts = run.get("timestamp", "")
        jira_key = run.get("jira_key")
        for item in run.get("assessments", []):
            req_id = item.get("requirement_id")
            if not req_id:
                continue
            entry = dict(item)
            entry["_run_id"] = run.get("run_id")
            entry["_timestamp"] = run_ts
            entry["_mode"] = run_mode
            entry["_jira_key"] = jira_key
            req_runs.setdefault(req_id, []).append(entry)

    authoritative_results: Dict[str, Dict[str, Any]] = {}
    provisional_items: List[Dict[str, Any]] = []
    disagreements: List[Dict[str, Any]] = []

    for req_id, req_data in req_map.items():
        runs_for_req = req_runs.get(req_id, [])

        if not runs_for_req:
            authoritative_results[req_id] = {
                "requirement_id": req_id,
                "requirement_text": req_data.get("requirement_text", ""),
                "status": "Not yet assessed",
                "flags": req_data.get("flags", []),
                "evidence": [],
                "delivering_pr": None,
                "claiming_tickets": [],
                "design_heading": req_data.get("source_citations", [{}])[0].get("heading_path", "Design Section"),
                "rationale": "Requirement has not yet been assessed against repository code.",
            }
            continue

        # Sort runs by timestamp descending (newest first)
        runs_for_req.sort(key=lambda x: x.get("_timestamp", ""), reverse=True)

        # Check for disagreements across runs
        unique_statuses = {r.get("status") for r in runs_for_req if r.get("status") not in ("Not yet assessed",)}
        if len(unique_statuses) > 1:
            disagreements.append(
                {
                    "requirement_id": req_id,
                    "requirement_text": req_data.get("requirement_text", ""),
                    "conflicting_statuses": list(unique_statuses),
                    "runs": [
                        {
                            "run_id": r.get("_run_id"),
                            "status": r.get("status"),
                            "jira_key": r.get("_jira_key"),
                            "timestamp": r.get("_timestamp"),
                        }
                        for r in runs_for_req
                    ],
                }
            )

        # Revalidate evidence against origin/main
        chosen_assessment: Optional[Dict[str, Any]] = None
        claiming_tickets = sorted(list({r.get("_jira_key") for r in runs_for_req if r.get("_jira_key")}))

        for candidate in runs_for_req:
            cand_mode = candidate.get("_mode")
            cand_status = candidate.get("status")
            ev_list = candidate.get("evidence", [])

            if cand_status == "Implemented":
                valid_on_main = False
                revalidated_evidence = []
                for ev in ev_list:
                    ok, new_line, reason = revalidate_evidence_on_baseline(ev, baseline_ctx, root)
                    if ok:
                        valid_on_main = True
                        ev_copy = dict(ev)
                        ev_copy["line_number"] = new_line
                        ev_copy["revalidation_note"] = reason
                        revalidated_evidence.append(ev_copy)

                if valid_on_main:
                    candidate_copy = dict(candidate)
                    candidate_copy["evidence"] = revalidated_evidence
                    candidate_copy["claiming_tickets"] = claiming_tickets
                    chosen_assessment = candidate_copy
                    break
                else:
                    # Preview or branch evidence not merged to main
                    provisional_items.append(
                        {
                            "requirement_id": req_id,
                            "requirement_text": req_data.get("requirement_text", ""),
                            "run_id": candidate.get("_run_id"),
                            "jira_key": candidate.get("_jira_key"),
                            "mode": cand_mode,
                            "evidence": ev_list,
                            "reason": "Evidence exists on feature branch / preview but is not yet merged to origin/main",
                        }
                    )
            elif cand_status in ("Partial", "Pending", "Unverifiable"):
                if cand_mode == "preview" and ev_list:
                    provisional_items.append(
                        {
                            "requirement_id": req_id,
                            "requirement_text": req_data.get("requirement_text", ""),
                            "run_id": candidate.get("_run_id"),
                            "jira_key": candidate.get("_jira_key"),
                            "mode": cand_mode,
                            "evidence": ev_list,
                            "reason": "Evidence on preview branch not yet verified on origin/main",
                        }
                    )
                candidate_copy = dict(candidate)
                candidate_copy["claiming_tickets"] = claiming_tickets
                chosen_assessment = candidate_copy
                break

        if not chosen_assessment:
            # Fallback to newest run or Not yet assessed
            newest = runs_for_req[0]
            authoritative_results[req_id] = {
                "requirement_id": req_id,
                "requirement_text": req_data.get("requirement_text", ""),
                "status": newest.get("status", "Not yet assessed") if newest.get("status") != "Implemented" else "Pending",
                "flags": newest.get("flags", []),
                "evidence": [],
                "delivering_pr": None,
                "claiming_tickets": claiming_tickets,
                "design_heading": req_data.get("source_citations", [{}])[0].get("heading_path", "Design Section"),
                "rationale": "No verified evidence active on origin/main baseline.",
            }
        else:
            delivering_pr = None
            if chosen_assessment.get("evidence"):
                delivering_pr = chosen_assessment["evidence"][0].get("pr_number") or chosen_assessment["evidence"][0].get("commit_sha")

            authoritative_results[req_id] = {
                "requirement_id": req_id,
                "requirement_text": req_data.get("requirement_text", ""),
                "status": chosen_assessment.get("status"),
                "flags": chosen_assessment.get("flags", []),
                "evidence": chosen_assessment.get("evidence", []),
                "delivering_pr": delivering_pr,
                "claiming_tickets": claiming_tickets,
                "design_heading": req_data.get("source_citations", [{}])[0].get("heading_path", "Design Section"),
                "rationale": chosen_assessment.get("rationale", ""),
            }

    # Counts and coverage percentage
    counts = {
        "Implemented": 0,
        "Partial": 0,
        "Pending": 0,
        "Unverifiable": 0,
        "Not yet assessed": 0,
    }
    for res in authoritative_results.values():
        st = res.get("status", "Not yet assessed")
        counts[st] = counts.get(st, 0) + 1

    total_applicable = sum(counts.values())
    coverage_pct = round((counts["Implemented"] / total_applicable * 100), 1) if total_applicable > 0 else 0.0

    return {
        "page_id": page_id,
        "baseline_commit": baseline_ctx.resolved_commit,
        "baseline_ref": baseline_ctx.requested_ref,
        "rollup_time": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "counts": counts,
        "coverage_percentage": coverage_pct,
        "authoritative_results": authoritative_results,
        "provisional_items": provisional_items,
        "disagreements": disagreements,
    }


def render_coverage_markdown(rollup_data: Dict[str, Any]) -> str:
    """Render COVERAGE.md in markdown format."""
    page_id = rollup_data["page_id"]
    commit = rollup_data["baseline_commit"][:8] if rollup_data["baseline_commit"] else "HEAD"
    counts = rollup_data["counts"]
    pct = rollup_data["coverage_percentage"]
    ts = rollup_data["rollup_time"]

    lines = [
        f"# Design Maturity Coverage: Confluence Page {page_id}",
        "",
        f"**Authoritative Baseline**: `{rollup_data['baseline_ref']}` ({commit})  ",
        f"**Rollup Generated**: {ts}  ",
        f"**Headline Implemented Coverage**: **{pct}%**  ",
        "",
        "### Maturity Status Summary",
        f"- **Implemented**: {counts['Implemented']}",
        f"- **Partial**: {counts['Partial']}",
        f"- **Pending**: {counts['Pending']}",
        f"- **Unverifiable**: {counts['Unverifiable']}",
        f"- **Not yet assessed**: {counts['Not yet assessed']}",
        f"- **Total Applicable Requirements**: {sum(counts.values())}",
        "",
        "---",
        "",
        "## Baseline Requirements Ledger",
        "",
        "| ID | Requirement | Status | Delivering PR/Commit | Claiming Tickets | Design Section | Evidence |",
        "|---|---|---|---|---|---|---|",
    ]

    for req_id, item in sorted(rollup_data["authoritative_results"].items()):
        req_text = item["requirement_text"].replace("|", "\\|")
        if len(req_text) > 70:
            req_text = req_text[:67] + "..."
        st = item["status"]
        pr = item["delivering_pr"] or "-"
        tickets = ", ".join(item["claiming_tickets"]) if item["claiming_tickets"] else "_no reviewed ticket claims this_"
        heading = item["design_heading"].replace("|", "\\|")
        ev_str = "-"
        if item.get("evidence"):
            e0 = item["evidence"][0]
            ev_str = f"`{e0.get('file_path')}:{e0.get('line_number')}`"

        lines.append(f"| {req_id} | {req_text} | **{st}** | {pr} | {tickets} | {heading} | {ev_str} |")

    # Gaps Section (Partial / Pending)
    lines.extend([
        "",
        "---",
        "",
        "## Implementation Gaps & Unclaimed Scope",
        "",
    ])

    gaps = [it for it in rollup_data["authoritative_results"].values() if it["status"] in ("Partial", "Pending")]
    if not gaps:
        lines.append("No active implementation gaps reported on baseline.")
    else:
        for g in gaps:
            req_id = g["requirement_id"]
            claim = ", ".join(g["claiming_tickets"]) if g["claiming_tickets"] else "no reviewed ticket claims this"
            lines.append(f"### {req_id}: {g['requirement_text']}")
            lines.append(f"- **Status**: `{g['status']}`")
            lines.append(f"- **Claiming Tickets**: {claim}")
            lines.append(f"- **Assessment Rationale**: {g.get('rationale', 'Pending implementation evidence')}")
            lines.append("")

    # Provisional Section
    lines.extend([
        "---",
        "",
        "## Provisional (Not on origin/main yet)",
        "",
    ])
    provisional = rollup_data.get("provisional_items", [])
    if not provisional:
        lines.append("No provisional branch evidence pending promotion.")
    else:
        for p in provisional:
            lines.append(
                f"- **{p['requirement_id']}** ({p.get('jira_key') or 'branch run'}): "
                f"{p['reason']}. Evidence in `{p['evidence'][0].get('file_path')}:{p['evidence'][0].get('line_number')}`."
            )

    # Disagreements Section
    if rollup_data.get("disagreements"):
        lines.extend([
            "",
            "---",
            "",
            "## Run Disagreements",
            "",
        ])
        for d in rollup_data["disagreements"]:
            lines.append(f"- **{d['requirement_id']}**: Conflicting statuses across runs: {', '.join(d['conflicting_statuses'])}")

    return "\n".join(lines) + "\n"


def run_rollup(page_id: str, repo_root: Optional[Path] = None, no_fetch: bool = True) -> Path:
    root = repo_root or find_repo_root()
    data = process_rollup(page_id, repo_root=root, no_fetch=no_fetch)
    md = render_coverage_markdown(data)

    status_dir = get_status_dir(page_id, root)
    coverage_file = status_dir / "COVERAGE.md"
    coverage_file.write_text(md, encoding="utf-8")
    return coverage_file


def main() -> int:
    parser = argparse.ArgumentParser(description="Deterministic rollup for DMR coverage.")
    parser.add_argument("--page-id", required=True, help="Confluence page ID")
    parser.add_argument("--no-fetch", action="store_true", default=True, help="Skip git fetch")
    args = parser.parse_args()

    out_file = run_rollup(args.page_id, no_fetch=args.no_fetch)
    print(json.dumps({"status": "SUCCESS", "coverage_file": str(out_file)}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
