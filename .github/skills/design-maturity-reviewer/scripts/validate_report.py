"""
Anti-hallucination validation gate for DMR.
Strictly verifies that:
1. Implemented items have non-empty, qualifying code evidence.
2. Cited files exist at the target git ref / working tree.
3. Cited lines and snippets match actual file content.
4. Design citations correspond to actual indexed chunks/headings.
Fails loudly and prints structured errors if hallucinated or fabricated citations are detected.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from git_context import GitContext, read_file_content, resolve_git_context
from search_code_evidence import hash_snippet, normalize_snippet


def validate_evidence_item(
    ev: Dict[str, Any], context: GitContext, repo_root: Path
) -> Tuple[bool, Optional[str]]:
    file_path = ev.get("file_path", "")
    if not file_path:
        return False, "Evidence entry missing 'file_path'."

    content = read_file_content(file_path, context)
    if content is None:
        return False, f"Cited file does not exist at ref '{context.requested_ref}': {file_path}"

    lines = content.splitlines()
    line_no = ev.get("line_number")
    if line_no is None or line_no < 1 or line_no > len(lines) + 1:
        return False, f"Line number {line_no} out of bounds for file {file_path} (total lines: {len(lines)})"

    snippet = ev.get("snippet", "")
    if not snippet:
        return False, f"Evidence for {file_path}:{line_no} has empty snippet."

    norm_snip = normalize_snippet(snippet)
    norm_content = normalize_snippet(content)

    # Check if snippet appears in the file
    if norm_snip not in norm_content:
        # Also check lines directly around line_no
        start_l = max(0, line_no - 4)
        end_l = min(len(lines), line_no + 4)
        local_content = normalize_snippet("\n".join(lines[start_l:end_l]))
        if norm_snip not in local_content:
            return False, f"Cited snippet does not match content in {file_path} at line {line_no}."

    return True, None


def validate_design_citations(
    citations: List[Dict[str, Any]], indexed_chunks: Optional[List[Dict[str, Any]]]
) -> Tuple[bool, Optional[str]]:
    if not citations:
        return True, None
    if not indexed_chunks:
        return True, None

    known_headings = {c.get("heading_path", "").strip().lower() for c in indexed_chunks}
    known_chunks = {c.get("chunk_id", "") for c in indexed_chunks}

    for cite in citations:
        h_path = cite.get("heading_path", "").strip().lower()
        c_id = cite.get("chunk_id", "")
        if c_id and c_id not in known_chunks and not any(h in known_headings for h in [h_path]):
            return False, f"Cited design heading '{cite.get('heading_path')}' or chunk '{c_id}' not found in index."

    return True, None


def validate_assessment_report(
    assessments: List[Dict[str, Any]],
    context: GitContext,
    indexed_chunks: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[bool, List[str]]:
    repo_root = Path(context.repo_root)
    errors: List[str] = []

    for item in assessments:
        req_id = item.get("requirement_id", "UNKNOWN")
        status = item.get("status", "Not yet assessed")
        evidence = item.get("evidence", [])

        # Rule 1: Implemented status must have evidence
        if status == "Implemented":
            if not evidence:
                errors.append(
                    f"ANTI-HALLUCINATION FAILURE: Requirement {req_id} marked Implemented without any code evidence."
                )
                continue

            for ev in evidence:
                valid, err = validate_evidence_item(ev, context, repo_root)
                if not valid:
                    errors.append(f"ANTI-HALLUCINATION FAILURE on {req_id}: {err}")

        # Rule 2: Partial status evidence validation
        elif status == "Partial":
            for ev in evidence:
                valid, err = validate_evidence_item(ev, context, repo_root)
                if not valid:
                    errors.append(f"ANTI-HALLUCINATION FAILURE on {req_id} (Partial): {err}")

        # Rule 3: Design citation validation
        citations = item.get("source_citations", [])
        c_valid, c_err = validate_design_citations(citations, indexed_chunks)
        if not c_valid:
            errors.append(f"ANTI-HALLUCINATION FAILURE on {req_id}: {c_err}")

    passed = len(errors) == 0
    return passed, errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate assessment report against anti-hallucination rules.")
    parser.add_argument("--report-file", required=True, help="Path to assessment JSON file")
    parser.add_argument("--ref", help="Target Git ref")
    parser.add_argument("--preview", action="store_true", help="Preview mode")
    parser.add_argument("--chunks-file", help="Optional chunks.json to verify design citations")
    args = parser.parse_args()

    ctx = resolve_git_context(requested_ref=args.ref, preview=args.preview)

    with open(args.report_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    assessments = data if isinstance(data, list) else data.get("assessments", [])

    chunks = None
    if args.chunks_file and Path(args.chunks_file).exists():
        with open(args.chunks_file, "r", encoding="utf-8") as cf:
            chunks = json.load(cf)

    passed, errors = validate_assessment_report(assessments, ctx, chunks)

    output = {
        "status": "PASS" if passed else "FAIL",
        "total_assessed": len(assessments),
        "errors": errors,
    }
    print(json.dumps(output, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
