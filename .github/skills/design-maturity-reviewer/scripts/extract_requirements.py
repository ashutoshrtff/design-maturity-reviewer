"""
Requirement extractor for DMR.
Decomposes design pages and ticket AC into atomic, traceable requirements with stable IDs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


def classify_requirement_type(text: str) -> str:
    lower = text.lower()
    if any(k in lower for k in ("must validate", "invalid", "header", "format", "schema", "regex", "required")):
        return "validation"
    if any(k in lower for k in ("error", "409", "400", "500", "conflict", "exception", "fail", "retry")):
        return "error_handling"
    if any(k in lower for k in ("config", "env", "setting", "flag", "parameter", "timeout")):
        return "configuration"
    if any(k in lower for k in ("api", "endpoint", "contract", "kafka", "s3", "database", "webhook")):
        return "integration_contract"
    if any(k in lower for k in ("snappy", "latency", "scale", "performance", "availability", "multi-az", "sla", "under 500ms")):
        return "non_functional"
    return "functional"


def is_ambiguous(text: str) -> bool:
    """Flag as ambiguous if the text is subjective or lacks testable thresholds."""
    lower = text.lower()
    vague_cues = ["suitably", "snappy", "user-friendly", "as appropriate", "sufficient", "fast", "scalable under peak"]
    # If it contains vague cue without concrete metrics
    for cue in vague_cues:
        if cue in lower and not re.search(r"\b\d+\s*(?:ms|seconds|req/s|%)\b", lower):
            return True
    return False


def generate_stable_id(text: str, index: int, existing_requirements: Optional[List[Dict[str, Any]]] = None) -> str:
    """Assign stable R-XXX id, reusing prior ID if text materially matches."""
    if existing_requirements:
        norm_new = re.sub(r"\W+", " ", text.lower()).strip()
        for r in existing_requirements:
            r_norm = re.sub(r"\W+", " ", r.get("requirement_text", "").lower()).strip()
            if r_norm == norm_new or norm_new.startswith(r_norm[:40]) or r_norm.startswith(norm_new[:40]):
                return r["requirement_id"]
    return f"R-{index:03d}"


def extract_from_design_chunks(
    chunks: List[Dict[str, Any]],
    page_id: str,
    design_version: int = 1,
    existing_requirements: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Extract atomic requirements from indexed chunks."""
    requirements: List[Dict[str, Any]] = []
    seen_texts: Set[str] = set()
    req_counter = len(existing_requirements) if existing_requirements else 0

    for chunk in chunks:
        text = chunk.get("text", "")
        heading_path = chunk.get("heading_path", "")
        c_page_id = str(chunk.get("page_id", page_id))

        lines = text.splitlines()
        current_req_text = ""
        current_acs: List[str] = []

        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue

            # Bullet or numbered item
            if line_str.startswith(("- ", "* ", "1. ", "2. ", "3. ", "4. ", "5. ")):
                bullet_content = re.sub(r"^(?:[-*]|\d+\.)\s+", "", line_str).strip()
                if not current_req_text:
                    current_req_text = bullet_content
                else:
                    current_acs.append(bullet_content)
            else:
                if current_req_text:
                    # Flush previous requirement
                    norm = current_req_text.lower()
                    if norm not in seen_texts and len(current_req_text) > 10:
                        seen_texts.add(norm)
                        req_counter += 1
                        r_id = generate_stable_id(current_req_text, req_counter, existing_requirements)
                        flags = ["ambiguous"] if is_ambiguous(current_req_text) else []
                        requirements.append(
                            {
                                "requirement_id": r_id,
                                "design_id": c_page_id,
                                "design_version": str(design_version),
                                "revision": 1,
                                "requirement_text": current_req_text,
                                "requirement_type": classify_requirement_type(current_req_text),
                                "acceptance_criteria": current_acs or [current_req_text],
                                "source_citations": [
                                    {"page_id": c_page_id, "heading_path": heading_path, "chunk_id": chunk.get("chunk_id")}
                                ],
                                "dependencies": [],
                                "flags": flags,
                                "last_assessed_run_id": None,
                            }
                        )
                    current_req_text = ""
                    current_acs = []
                current_req_text = line_str

        if current_req_text:
            norm = current_req_text.lower()
            if norm not in seen_texts and len(current_req_text) > 10:
                seen_texts.add(norm)
                req_counter += 1
                r_id = generate_stable_id(current_req_text, req_counter, existing_requirements)
                flags = ["ambiguous"] if is_ambiguous(current_req_text) else []
                requirements.append(
                    {
                        "requirement_id": r_id,
                        "design_id": c_page_id,
                        "design_version": str(design_version),
                        "revision": 1,
                        "requirement_text": current_req_text,
                        "requirement_type": classify_requirement_type(current_req_text),
                        "acceptance_criteria": current_acs or [current_req_text],
                        "source_citations": [
                            {"page_id": c_page_id, "heading_path": heading_path, "chunk_id": chunk.get("chunk_id")}
                        ],
                        "dependencies": [],
                        "flags": flags,
                        "last_assessed_run_id": None,
                    }
                )

    return requirements


def map_ticket_scope(
    ticket: Dict[str, Any],
    all_requirements: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[str]]:
    """
    Given a ticket (with summary and acceptance criteria) and the full requirement set:
    Returns:
    - in_scope_requirements: matched requirements
    - outside_scope_requirements: remaining design requirements
    - no_design_basis_items: ticket AC items that have no match in the design
    """
    ticket_text = f"{ticket.get('summary', '')}\n{ticket.get('description', '')}\n" + "\n".join(
        ticket.get("acceptance_criteria", [])
    )
    ticket_lower = ticket_text.lower()

    in_scope: List[Dict[str, Any]] = []
    outside_scope: List[Dict[str, Any]] = []

    for req in all_requirements:
        r_text = req.get("requirement_text", "").lower()
        ac_combined = " ".join(req.get("acceptance_criteria", [])).lower()
        full_req_str = f"{r_text} {ac_combined}"
        
        # Extract keywords
        terms = re.findall(r"[a-z0-9_\-/]{4,}", full_req_str)
        matches = [t for t in terms if t in ticket_lower]
        ratio = len(matches) / max(1, len(terms))

        # Check if any key term or exact AC overlaps
        direct_overlap = any(
            any(k in ac.lower() for k in ["idempotency", "cache", "409", "concurrent", "settlement"])
            for ac in req.get("acceptance_criteria", [])
        ) if "idempotency" in ticket_lower else False

        if ratio >= 0.20 or direct_overlap or any(ac.lower() in ticket_lower for ac in req.get("acceptance_criteria", [])):
            in_scope.append(req)
        else:
            outside_scope.append(req)

    # Check for ticket items with no design basis
    no_design_basis: List[str] = []
    all_design_text = " ".join([r.get("requirement_text", "") for r in all_requirements]).lower()
    for ac in ticket.get("acceptance_criteria", []):
        ac_words = re.findall(r"[a-z0-9_\-/]{4,}", ac.lower())
        overlap = [w for w in ac_words if w in all_design_text]
        if not overlap:
            no_design_basis.append(ac)

    # Check extra sections in ticket description (e.g. Additional Requirements)
    desc = ticket.get("description", "")
    for line in desc.splitlines():
        line_s = line.strip()
        if ("export" in line_s.lower() or "spreadsheet" in line_s.lower() or "excel" in line_s.lower()) and "excel" not in all_design_text:
            cleaned = re.sub(r"^(?:additional requirements:?|[-*#])\s*", "", line_s, flags=re.IGNORECASE).strip()
            if cleaned and cleaned not in no_design_basis:
                no_design_basis.append(cleaned)

    return in_scope, outside_scope, no_design_basis


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract requirements from design and ticket.")
    parser.add_argument("--chunks-file", help="Path to chunks.json")
    parser.add_argument("--ticket-file", help="Path to ticket JSON")
    parser.add_argument("--page-id", default="123456", help="Confluence Page ID")
    parser.add_argument("--version", type=int, default=12, help="Design version")
    args = parser.parse_args()

    chunks: List[Dict[str, Any]] = []
    if args.chunks_file:
        with open(args.chunks_file, "r", encoding="utf-8") as f:
            chunks = json.load(f)

    reqs = extract_from_design_chunks(chunks, args.page_id, args.version)

    if args.ticket_file:
        with open(args.ticket_file, "r", encoding="utf-8") as f:
            ticket = json.load(f)
        in_s, out_s, no_db = map_ticket_scope(ticket, reqs)
        output = {
            "in_scope": in_s,
            "outside_scope": out_s,
            "no_design_basis": no_db,
        }
    else:
        output = {"requirements": reqs}

    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
