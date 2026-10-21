"""
Requirement assessment engine for DMR.
Evaluates code evidence and design context against requirement acceptance criteria
to determine implementation status: Implemented, Partial, Pending, Unverifiable, or Not yet assessed.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from attribute_evidence import attribute_line
from git_context import GitContext, resolve_git_context
from search_code_evidence import hash_snippet, search_code_evidence


def evaluate_requirement(
    req: Dict[str, Any],
    context: GitContext,
    search_paths: Optional[List[str]] = None,
    github_hostname: str = "",
) -> Dict[str, Any]:
    """
    Assess a single requirement against code evidence at the given git ref.
    """
    req_id = req.get("requirement_id", "R-UNKNOWN")
    req_text = req.get("requirement_text", "")
    acs = req.get("acceptance_criteria", [req_text])
    flags = list(req.get("flags", []))

    if context.mode == "preview":
        if "provisional" not in flags:
            flags.append("provisional")

    # If already flagged as ambiguous or non-functional without metrics
    if "ambiguous" in flags or is_vague_requirement(req_text):
        if "ambiguous" not in flags:
            flags.append("ambiguous")
        return {
            "requirement_id": req_id,
            "requirement_text": req_text,
            "source_citations": req.get("source_citations", []),
            "status": "Unverifiable",
            "flags": flags,
            "rationale": "Design specification is ambiguous or lacks verifiable criteria.",
            "evidence": [],
            "missing_criteria": acs,
            "human_verification_needed": "Product/Architect must clarify testable thresholds.",
        }

    # Non-functional / infrastructure requirements that code cannot prove
    lower_req = req_text.lower()
    if any(k in lower_req for k in ("multi-az", "failover", "under 500ms", "availability zone", "sla")):
        return {
            "requirement_id": req_id,
            "requirement_text": req_text,
            "source_citations": req.get("source_citations", []),
            "status": "Unverifiable",
            "flags": flags,
            "rationale": "Infrastructure and cross-AZ failover SLA cannot be proven through source code alone.",
            "evidence": [],
            "missing_criteria": acs,
            "human_verification_needed": "Verify AWS RDS multi-AZ configuration, CloudWatch latency metrics, and chaos failover drill reports.",
        }

    # Extract search terms from requirement text and each AC
    search_terms: List[str] = []
    # Key tokens
    for token in re.findall(r'["`\']([^"`\']+)["`\']', req_text + " " + " ".join(acs)):
        search_terms.append(token)
    for ep in re.findall(r'(/(?:v\d+/)?[\w\-]+(?:/[\w\-]+)*)', req_text + " " + " ".join(acs)):
        search_terms.append(ep)
    for code in re.findall(r'\b[A-Z][A-Z0-9_]{3,35}\b', req_text + " " + " ".join(acs)):
        if code not in ("HTTP", "JSON", "POST", "GET"):
            search_terms.append(code)
    for field in re.findall(r'\b[a-z][a-z0-9_]{3,30}_[a-z0-9_]+\b', req_text + " " + " ".join(acs)):
        search_terms.append(field)

    search_terms = list(set(search_terms))
    evidence_list = search_code_evidence(search_terms, context, search_paths)

    if not evidence_list:
        return {
            "requirement_id": req_id,
            "requirement_text": req_text,
            "source_citations": req.get("source_citations", []),
            "status": "Pending",
            "flags": flags,
            "rationale": f"Targeted search for terms {search_terms[:5]} found no qualifying implementation evidence in code at ref {context.requested_ref}.",
            "evidence": [],
            "missing_criteria": acs,
            "human_verification_needed": None,
        }

    # Check which ACs are evidenced
    satisfied_acs: List[str] = []
    missing_acs: List[str] = []
    all_evidence_text = "\n".join([e.get("snippet", "") for e in evidence_list])

    for ac in acs:
        # Check if AC key terms appear in code evidence
        ac_terms = re.findall(r'["`\']([^"`\']+)["`\']|\b[A-Z0-9_]{4,}\b|\b[a-z0-9_]{4,}_[a-z0-9_]+\b', ac)
        flattened_terms = [t for sub in ac_terms for t in (sub if isinstance(sub, tuple) else [sub]) if t and t not in ("HTTP", "JSON")]
        
        if not flattened_terms:
            # Check general words
            words = [w for w in re.findall(r'[a-zA-Z]{4,}', ac) if w.lower() not in ("return", "with", "when", "that", "this", "from")]
            matches = [w for w in words if w.lower() in all_evidence_text.lower()]
            if len(matches) >= max(1, len(words) // 2):
                satisfied_acs.append(ac)
            else:
                missing_acs.append(ac)
        else:
            matches = [t for t in flattened_terms if t in all_evidence_text or t.lower() in all_evidence_text.lower()]
            if len(matches) == len(flattened_terms):
                satisfied_acs.append(ac)
            else:
                missing_acs.append(ac)

    # Attribute each piece of evidence
    attributed_evidence: List[Dict[str, Any]] = []
    for ev in evidence_list[:5]:
        attr = attribute_line(ev["file_path"], ev["line_number"], context, github_hostname)
        ev_copy = dict(ev)
        ev_copy.update(attr)
        attributed_evidence.append(ev_copy)

    if not missing_acs:
        status = "Implemented"
        rationale = f"All {len(acs)} acceptance criteria are satisfied by code evidence at {context.requested_ref}."
    elif satisfied_acs and missing_acs:
        status = "Partial"
        rationale = f"Partial implementation evidenced ({len(satisfied_acs)}/{len(acs)} criteria). Missing: {'; '.join(missing_acs[:2])}"
    else:
        status = "Pending"
        rationale = "Candidate code references found but required acceptance criteria semantics are not satisfied."

    return {
        "requirement_id": req_id,
        "requirement_text": req_text,
        "source_citations": req.get("source_citations", []),
        "status": status,
        "flags": flags,
        "rationale": rationale,
        "evidence": attributed_evidence,
        "satisfied_criteria": satisfied_acs,
        "missing_criteria": missing_acs,
        "human_verification_needed": None,
    }


def is_vague_requirement(text: str) -> bool:
    lower = text.lower()
    return any(cue in lower for cue in ("suitably", "snappy", "user-friendly", "as appropriate", "sufficient"))


def assess_requirements_list(
    requirements: List[Dict[str, Any]],
    context: GitContext,
    search_paths: Optional[List[str]] = None,
    github_hostname: str = "",
) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for r in requirements:
        assessment = evaluate_requirement(r, context, search_paths, github_hostname)
        results.append(assessment)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Assess requirements against code evidence.")
    parser.add_argument("--requirements-file", required=True, help="Path to requirements JSON")
    parser.add_argument("--ref", help="Target git ref")
    parser.add_argument("--preview", action="store_true", help="Preview mode")
    parser.add_argument("--paths", nargs="+", default=["."], help="Search paths")
    args = parser.parse_args()

    ctx = resolve_git_context(requested_ref=args.ref, preview=args.preview)
    with open(args.requirements_file, "r", encoding="utf-8") as f:
        reqs = json.load(f)
    if isinstance(reqs, dict) and "requirements" in reqs:
        reqs = reqs["requirements"]

    assessments = assess_requirements_list(reqs, ctx, args.paths)
    print(json.dumps(assessments, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
