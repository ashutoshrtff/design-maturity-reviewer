"""
Ledger manager for Design Maturity Reviewer.
Maintains conflict-safe, immutable run records under design-status/<pageId>/runs/
and manages the requirements checklist in requirements.json.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import secrets
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from config_loader import find_repo_root


def get_status_dir(page_id: str, repo_root: Optional[Path] = None, base_status_dir: str = "design-status") -> Path:
    root = repo_root or find_repo_root()
    p = root / base_status_dir / page_id
    p.mkdir(parents=True, exist_ok=True)
    (p / "runs").mkdir(parents=True, exist_ok=True)
    (p / "tickets").mkdir(parents=True, exist_ok=True)
    return p


def generate_unique_run_id(prefix: str = "run") -> str:
    now_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S")
    rand_suffix = secrets.token_hex(3)
    return f"{prefix}-{now_str}-{rand_suffix}"


def save_run_record(
    page_id: str,
    run_data: Dict[str, Any],
    repo_root: Optional[Path] = None,
    base_status_dir: str = "design-status",
) -> Path:
    status_dir = get_status_dir(page_id, repo_root, base_status_dir)
    run_id = run_data.get("run_id") or generate_unique_run_id(run_data.get("jira_key") or "run")
    run_data["run_id"] = run_id
    run_data.setdefault("timestamp", datetime.datetime.now(datetime.timezone.utc).isoformat())

    run_file = status_dir / "runs" / f"{run_id}.json"

    # Atomic write via temporary file
    temp_file = status_dir / "runs" / f".{run_id}.tmp"
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(run_data, f, indent=2, ensure_ascii=False)
    temp_file.replace(run_file)

    # Append to history.jsonl
    history_file = status_dir / "history.jsonl"
    summary_entry = {
        "run_id": run_id,
        "timestamp": run_data.get("timestamp"),
        "jira_key": run_data.get("jira_key"),
        "mode": run_data.get("git_context", {}).get("mode", "verified"),
        "ref": run_data.get("git_context", {}).get("requested_ref", ""),
        "commit": run_data.get("git_context", {}).get("resolved_commit", ""),
        "assessed_count": len(run_data.get("assessments", [])),
    }
    with open(history_file, "a", encoding="utf-8") as hf:
        hf.write(json.dumps(summary_entry) + "\n")

    return run_file


def load_requirements(page_id: str, repo_root: Optional[Path] = None, base_status_dir: str = "design-status") -> List[Dict[str, Any]]:
    status_dir = get_status_dir(page_id, repo_root, base_status_dir)
    req_file = status_dir / "requirements.json"
    if not req_file.exists():
        return []
    with open(req_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else data.get("requirements", [])


def save_requirements(
    page_id: str,
    requirements: List[Dict[str, Any]],
    repo_root: Optional[Path] = None,
    base_status_dir: str = "design-status",
) -> Path:
    status_dir = get_status_dir(page_id, repo_root, base_status_dir)
    req_file = status_dir / "requirements.json"
    temp_file = status_dir / ".requirements.json.tmp"
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(requirements, f, indent=2, ensure_ascii=False)
    temp_file.replace(req_file)
    return req_file


def list_run_records(
    page_id: str, repo_root: Optional[Path] = None, base_status_dir: str = "design-status"
) -> List[Dict[str, Any]]:
    status_dir = get_status_dir(page_id, repo_root, base_status_dir)
    runs_dir = status_dir / "runs"
    runs: List[Dict[str, Any]] = []

    for fpath in sorted(runs_dir.glob("*.json")):
        if fpath.name.startswith("."):
            continue
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
                runs.append(data)
        except Exception:
            continue
    return runs


def get_latest_known_statuses(
    page_id: str, repo_root: Optional[Path] = None, base_status_dir: str = "design-status"
) -> Dict[str, Dict[str, Any]]:
    """Return latest known status for each requirement across previous runs."""
    runs = list_run_records(page_id, repo_root, base_status_dir)
    known: Dict[str, Dict[str, Any]] = {}

    for run in runs:
        # Sort runs chronologically
        r_id = run.get("run_id", "")
        ts = run.get("timestamp", "")
        mode = run.get("git_context", {}).get("mode", "verified")
        jira_key = run.get("jira_key")

        for item in run.get("assessments", []):
            req_id = item.get("requirement_id")
            if not req_id:
                continue
            # Store or update latest
            known[req_id] = {
                "requirement_id": req_id,
                "status": item.get("status", "Not yet assessed"),
                "flags": item.get("flags", []),
                "run_id": r_id,
                "timestamp": ts,
                "mode": mode,
                "jira_key": jira_key,
                "evidence_count": len(item.get("evidence", [])),
            }

    return known


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage DMR ledger and run records.")
    parser.add_argument("--page-id", required=True, help="Confluence page ID")
    parser.add_argument("--list-runs", action="store_true", help="List all recorded runs")
    parser.add_argument("--latest-statuses", action="store_true", help="Print latest status per requirement")
    args = parser.parse_args()

    if args.list_runs:
        runs = list_run_records(args.page_id)
        print(json.dumps([{"run_id": r.get("run_id"), "timestamp": r.get("timestamp")} for r in runs], indent=2))
        return 0

    if args.latest_statuses:
        statuses = get_latest_known_statuses(args.page_id)
        print(json.dumps(statuses, indent=2))
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
