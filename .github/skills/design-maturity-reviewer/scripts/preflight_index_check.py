"""
Preflight index checker for DMR.
Verifies manifest presence, schema, version freshness, and checks whether
local knowledge-index and design-status are behind origin/main.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from config_loader import find_repo_root, load_config
from git_context import resolve_git_context, run_git_cmd


def check_behind_origin(
    repo_root: Path, baseline_ref: str = "origin/main", paths: Optional[List[str]] = None
) -> Tuple[bool, str]:
    """Check if local knowledge-index/ or design-status/ differ from origin/main."""
    target_paths = paths or ["knowledge-index", "design-status"]
    code, out, _ = run_git_cmd(["diff", "--stat", baseline_ref, "--"] + target_paths, cwd=repo_root)
    if code == 0 and out.strip():
        return True, out.strip()
    return False, ""


def run_preflight(
    page_id: str,
    mode: str = "ticket",
    baseline_ref: str = "origin/main",
    repo_root: Optional[Path] = None,
    no_fetch: bool = True,
) -> Tuple[bool, Dict[str, Any]]:
    root = repo_root or find_repo_root()
    cfg = load_config(repo_root=root)
    index_base = root / cfg.get("knowledge", {}).get("index_dir", "knowledge-index")
    page_index_dir = index_base / page_id

    manifest_path = page_index_dir / "manifest.json"
    chunks_path = page_index_dir / "chunks.json"

    # 1. Missing Index check
    if not manifest_path.exists() or not chunks_path.exists():
        ingest_cmd = cfg.get("knowledge", {}).get(
            "ingestion_command",
            f"python tools/knowledge-ingestion/ingest.py --page-id {page_id} --output knowledge-index/{page_id}",
        ).replace("{page_id}", page_id)
        return False, {
            "status": "FAIL",
            "reason": "MISSING_INDEX",
            "page_id": page_id,
            "message": f"Page {page_id} isn't ingested. Run ingestion first: '{ingest_cmd}'",
            "ingest_command": ingest_cmd,
        }

    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    except Exception as e:
        return False, {
            "status": "FAIL",
            "reason": "CORRUPT_MANIFEST",
            "page_id": page_id,
            "message": f"Index manifest for page {page_id} is corrupt: {e}",
        }

    # 2. Behind origin check
    differs_from_origin, diff_stat = check_behind_origin(root, baseline_ref)
    behind_warning = None
    if differs_from_origin:
        behind_warning = (
            "Your local knowledge-index or design-status differs from origin/main. "
            "Your index or ledger may be out of date. Merge or rebase main."
        )
        if mode == "baseline":
            # For Mode B, require matching origin/main
            return False, {
                "status": "FAIL",
                "reason": "BEHIND_ORIGIN_BASELINE",
                "page_id": page_id,
                "message": (
                    "Baseline coverage mode requires local index and ledger to match origin/main. "
                    f"Differences detected:\n{diff_stat}\nPlease merge or rebase main before running Mode B."
                ),
            }

    # 3. Optional remote freshness check
    base_url = os.getenv("ATLASSIAN_BASE_URL")
    pat = os.getenv("ATLASSIAN_PAT") or os.getenv("ATLASSIAN_API_TOKEN")
    stale_warning = None

    if base_url and pat:
        try:
            import requests

            headers = {"Authorization": f"Bearer {pat}", "Accept": "application/json"}
            res = requests.get(f"{base_url.rstrip('/')}/rest/api/content/{page_id}?expand=version", headers=headers, timeout=5)
            if res.status_code == 200:
                remote_ver = res.json().get("version", {}).get("number")
                indexed_ver = manifest.get("page_version")
                if remote_ver and indexed_ver and remote_ver > indexed_ver:
                    stale_warning = (
                        f"Index may be STALE: Indexed version is {indexed_ver} ({manifest.get('ingested_at')}), "
                        f"but remote Confluence version is {remote_ver}."
                    )
        except Exception:
            pass

    return True, {
        "status": "PASS",
        "page_id": page_id,
        "page_title": manifest.get("page_title"),
        "page_version": manifest.get("page_version"),
        "ingested_at": manifest.get("ingested_at"),
        "chunk_count": manifest.get("chunk_count"),
        "behind_warning": behind_warning,
        "stale_warning": stale_warning,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Preflight index and branch check for DMR.")
    parser.add_argument("--page-id", required=True, help="Confluence page ID")
    parser.add_argument("--mode", choices=["ticket", "baseline"], default="ticket", help="Operating mode")
    parser.add_argument("--baseline-ref", default="origin/main", help="Baseline ref to check against")
    args = parser.parse_args()

    passed, res = run_preflight(args.page_id, mode=args.mode, baseline_ref=args.baseline_ref)
    print(json.dumps(res, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
