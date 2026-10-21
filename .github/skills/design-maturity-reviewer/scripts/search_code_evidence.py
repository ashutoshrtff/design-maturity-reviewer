"""
Code evidence searcher for Design Maturity Reviewer.
Derives search terms from requirements, runs ref-aware git grep or working-tree search,
and extracts bounded snippets with normalized SHA-256 hashes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from config_loader import load_config
from git_context import GitContext, read_file_content, resolve_git_context, run_git_cmd


def normalize_snippet(snippet: str) -> str:
    """Normalize line endings and outer whitespace for robust fingerprinting."""
    lines = [line.rstrip() for line in snippet.strip().splitlines()]
    return "\n".join(lines)


def hash_snippet(snippet: str) -> str:
    norm = normalize_snippet(snippet)
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def extract_terms_from_text(text: str) -> List[str]:
    """
    Extract high-value search terms from requirement text or acceptance criteria:
    - Endpoints e.g. /v1/settlements
    - UPPER_SNAKE_CASE error codes / enums e.g. IDEMPOTENCY_CONCURRENT_REQUEST
    - camelCase / PascalCase method or class names e.g. IdempotencyKey, calculated_fee_cents
    - Quoted strings e.g. "Idempotency-Key", "X-Cache"
    """
    terms: Set[str] = set()

    # Quoted strings
    for m in re.finditer(r'["`\']([^"`\']{3,60})["`\']', text):
        terms.add(m.group(1).strip())

    # Endpoints
    for m in re.finditer(r'(/(?:v\d+/)?[\w\-]+(?:/[\w\-]+)*)', text):
        terms.add(m.group(1).strip())

    # Error codes / UPPER_SNAKE_CASE
    for m in re.finditer(r'\b[A-Z][A-Z0-9_]{3,40}\b', text):
        terms.add(m.group(0).strip())

    # snake_case fields / config keys
    for m in re.finditer(r'\b[a-z][a-z0-9_]{3,35}_[a-z0-9_]+\b', text):
        terms.add(m.group(0).strip())

    # PascalCase or camelCase identifiers
    for m in re.finditer(r'\b[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]+)+\b', text):
        terms.add(m.group(0).strip())

    # Filter out common stop words
    stop = {"HTTP", "JSON", "REST", "POST", "GET", "PUT", "DELETE", "TRUE", "FALSE", "NULL"}
    terms = {t for t in terms if t not in stop and len(t) >= 3}
    return sorted(list(terms))


def extract_snippet_from_lines(
    lines: List[str], match_idx: int, context_lines: int = 3
) -> Tuple[int, int, str]:
    """Extract snippet centered on match_idx (0-based) with ±context_lines."""
    start_idx = max(0, match_idx - context_lines)
    end_idx = min(len(lines), match_idx + context_lines + 1)
    snippet = "\n".join(lines[start_idx:end_idx])
    return start_idx + 1, end_idx, snippet


def search_committed_ref(
    repo_root: Path,
    commit_sha: str,
    terms: List[str],
    search_paths: List[str],
    max_results_per_term: int = 5,
) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    seen_snippets: Set[str] = set()

    for term in terms:
        # Build git grep command: git grep -n -I -F <term> <commit> -- <paths>
        args = ["grep", "-n", "-I", "-F", term, commit_sha, "--"] + search_paths
        code, out, _ = run_git_cmd(args, cwd=repo_root)
        if code != 0 or not out:
            continue

        matches = out.splitlines()[:max_results_per_term]
        for m_line in matches:
            # Format from git grep <sha>: <sha>:<path>:<line_num>:<line_text>
            parts = m_line.split(":", 3)
            if len(parts) >= 4:
                file_path = parts[1]
                try:
                    line_no = int(parts[2])
                except ValueError:
                    continue

                # Fetch full file to get ±3 lines context
                show_code, content, _ = run_git_cmd(["show", f"{commit_sha}:{file_path}"], cwd=repo_root)
                if show_code == 0 and content:
                    lines = content.splitlines()
                    start_l, end_l, snip = extract_snippet_from_lines(lines, line_no - 1, context_lines=3)
                    snip_hash = hash_snippet(snip)
                    if snip_hash in seen_snippets:
                        continue
                    seen_snippets.add(snip_hash)

                    results.append(
                        {
                            "file_path": file_path,
                            "line_number": line_no,
                            "start_line": start_l,
                            "end_line": end_l,
                            "snippet": snip,
                            "snippet_hash": snip_hash,
                            "matched_term": term,
                            "ref": commit_sha[:8],
                        }
                    )

    return results


def search_working_tree(
    repo_root: Path,
    terms: List[str],
    search_paths: List[str],
    max_results_per_term: int = 5,
) -> List[Dict[str, Any]]:
    """Search working tree files (including untracked and modified files) in preview mode."""
    results: List[Dict[str, Any]] = []
    seen_snippets: Set[str] = set()

    candidate_files: List[Path] = []
    for sp in search_paths:
        p = repo_root / sp
        if p.is_file():
            candidate_files.append(p)
        elif p.is_dir():
            for root, dirs, files in os.walk(p):
                # Skip .git, __pycache__, node_modules
                dirs[:] = [d for d in dirs if d not in (".git", "__pycache__", "node_modules", "vendor")]
                for f in files:
                    if not f.endswith((".py", ".ts", ".js", ".go", ".java", ".json", ".yaml", ".yml", ".sql")):
                        continue
                    candidate_files.append(Path(root) / f)

    for term in terms:
        term_matches = 0
        for fpath in candidate_files:
            if term_matches >= max_results_per_term:
                break
            try:
                content = fpath.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

            lines = content.splitlines()
            for idx, line in enumerate(lines):
                if term in line:
                    rel_path = str(fpath.relative_to(repo_root)).replace("\\", "/")
                    start_l, end_l, snip = extract_snippet_from_lines(lines, idx, context_lines=3)
                    snip_hash = hash_snippet(snip)
                    if snip_hash in seen_snippets:
                        continue
                    seen_snippets.add(snip_hash)

                    results.append(
                        {
                            "file_path": rel_path,
                            "line_number": idx + 1,
                            "start_line": start_l,
                            "end_line": end_l,
                            "snippet": snip,
                            "snippet_hash": snip_hash,
                            "matched_term": term,
                            "ref": "working-tree (preview)",
                        }
                    )
                    term_matches += 1
                    if term_matches >= max_results_per_term:
                        break

    return results


def search_code_evidence(
    terms: List[str],
    context: GitContext,
    search_paths: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    root = Path(context.repo_root)
    paths = search_paths or ["."]

    if context.mode == "preview":
        return search_working_tree(root, terms, paths)
    else:
        return search_committed_ref(root, context.resolved_commit, terms, paths)


def main() -> int:
    parser = argparse.ArgumentParser(description="Search code evidence at a specific Git reference.")
    parser.add_argument("--ref", help="Target Git ref (default: origin/main)")
    parser.add_argument("--preview", action="store_true", help="Inspect working tree in preview mode")
    parser.add_argument("--terms", nargs="+", help="Explicit search terms")
    parser.add_argument("--requirement-text", help="Requirement text to extract terms from")
    parser.add_argument("--paths", nargs="+", default=["."], help="Search path filters")
    args = parser.parse_args()

    ctx = resolve_git_context(requested_ref=args.ref, preview=args.preview)
    terms: List[str] = []
    if args.terms:
        terms.extend(args.terms)
    if args.requirement_text:
        terms.extend(extract_terms_from_text(args.requirement_text))

    evidence = search_code_evidence(terms, ctx, args.paths)
    print(json.dumps(evidence, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
