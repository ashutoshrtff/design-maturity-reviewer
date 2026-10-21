"""
PR evidence finder for Design Maturity Reviewer with 3-level fallback:
Level 1: GitHub CLI (gh) / API
Level 2: Git commit log search & squash/merge message parsing
Level 3: Working branch diff against origin/main
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from config_loader import load_config
from git_context import GitContext, get_repo_root, resolve_git_context, run_git_cmd


def try_level_1_gh(
    jira_key: str, repo_root: Path, hostname: str = "", pr_number: Optional[int] = None
) -> Optional[Dict[str, Any]]:
    """Level 1: Query GitHub CLI for PR associated with Jira ticket or specific PR number."""
    if pr_number is not None:
        cmd = ["pr", "view", str(pr_number), "--json", "number,title,state,headRefName,files,additions,deletions"]
    else:
        cmd = [
            "pr",
            "list",
            "--state",
            "all",
            "--search",
            jira_key,
            "--limit",
            "1",
            "--json",
            "number,title,state,headRefName,files,additions,deletions",
        ]

    if hostname:
        cmd.extend(["--hostname", hostname])

    try:
        proc = subprocess.run(["gh"] + cmd, cwd=str(repo_root), capture_output=True, text=True, check=False)
        if proc.returncode == 0 and proc.stdout.strip():
            data = json.loads(proc.stdout)
            if isinstance(data, list):
                if not data:
                    return None
                pr = data[0]
            else:
                pr = data

            files = [f.get("path", "") for f in pr.get("files", []) if isinstance(f, dict)]
            adds = pr.get("additions", 0)
            dels = pr.get("deletions", 0)
            return {
                "level": 1,
                "attribution_method": "gh_cli",
                "pr_number": pr.get("number"),
                "title": pr.get("title", ""),
                "state": pr.get("state", "UNKNOWN"),
                "branch": pr.get("headRefName", ""),
                "changed_files": files[:30],
                "diff_stat": f"+{adds}/-{dels} across {len(files)} files",
                "attribution_limitations": "Direct GitHub CLI verification",
            }
    except Exception:
        pass
    return None


def try_level_2_git_log(jira_key: str, repo_root: Path, ref: str = "HEAD") -> Optional[Dict[str, Any]]:
    """Level 2: Search git history for Jira key and extract PR numbers from commit messages."""
    code, out, _ = run_git_cmd(
        ["log", ref, "--grep", jira_key, "--pretty=format:%H%x09%s", "-n", "10"], cwd=repo_root
    )
    if code != 0 or not out:
        # Also check without grep if Jira key might be in merge commits
        code, out, _ = run_git_cmd(["log", ref, "--merges", "--pretty=format:%H%x09%s", "-n", "20"], cwd=repo_root)

    if code == 0 and out:
        for line in out.splitlines():
            parts = line.split("\t", 1)
            sha = parts[0]
            msg = parts[1] if len(parts) > 1 else ""

            # Check if line contains jira key or PR references
            if jira_key in msg or "#" in msg:
                # Look for (#123) or 'Merge pull request #123'
                pr_match = re.search(r"\(#(\d+)\)|Merge pull request #(\d+)", msg)
                pr_num = int(pr_match.group(1) or pr_match.group(2)) if pr_match else None

                # Get changed files and diffstat for this commit
                stat_code, stat_out, _ = run_git_cmd(["show", "--stat", "--oneline", sha], cwd=repo_root)
                file_code, file_out, _ = run_git_cmd(
                    ["diff-tree", "--no-commit-id", "--name-only", "-r", sha], cwd=repo_root
                )
                files = file_out.splitlines() if file_code == 0 else []

                stat_line = stat_out.splitlines()[-1] if stat_code == 0 and stat_out else "1 commit"

                return {
                    "level": 2,
                    "attribution_method": "git_history",
                    "pr_number": pr_num,
                    "title": msg,
                    "state": "MERGED" if pr_num else "COMMITTED",
                    "branch": "history",
                    "commit_sha": sha[:8],
                    "changed_files": files[:30],
                    "diff_stat": stat_line,
                    "attribution_limitations": "Inferred from git commit message; GitHub metadata was not queried",
                }
    return None


def try_level_3_branch_diff(repo_root: Path, base_ref: str = "origin/main") -> Dict[str, Any]:
    """Level 3: When no PR exists yet, review branch diff against baseline."""
    code, out, _ = run_git_cmd(["diff", f"{base_ref}...HEAD", "--stat"], cwd=repo_root)
    file_code, file_out, _ = run_git_cmd(["diff", f"{base_ref}...HEAD", "--name-only"], cwd=repo_root)

    files = file_out.splitlines() if file_code == 0 else []
    stat_line = out.splitlines()[-1] if code == 0 and out else "Local branch changes"

    return {
        "level": 3,
        "attribution_method": "branch_changes",
        "pr_number": None,
        "title": "Local working branch (unmerged)",
        "state": "PROVISIONAL",
        "branch": "HEAD",
        "changed_files": files[:30],
        "diff_stat": stat_line,
        "attribution_limitations": "No PR found; using branch changes relative to origin/main",
    }


def find_pr_evidence(
    jira_key: str,
    context: GitContext,
    github_hostname: str = "",
    pr_number: Optional[int] = None,
) -> Dict[str, Any]:
    repo_root = Path(context.repo_root)

    # 1. Try Level 1
    res1 = try_level_1_gh(jira_key, repo_root, hostname=github_hostname, pr_number=pr_number)
    if res1:
        return res1

    # 2. Try Level 2
    res2 = try_level_2_git_log(jira_key, repo_root, ref=context.resolved_commit)
    if res2:
        return res2

    # 3. Fallback to Level 3
    return try_level_3_branch_diff(repo_root, base_ref=context.base_ref)


def main() -> int:
    parser = argparse.ArgumentParser(description="Find PR evidence using 3-level fallback.")
    parser.add_argument("--jira-key", required=True, help="Jira Ticket Key")
    parser.add_argument("--pr", type=int, help="Optional explicit PR number")
    parser.add_argument("--ref", help="Target git ref")
    parser.add_argument("--preview", action="store_true", help="Preview mode")
    parser.add_argument("--hostname", default="", help="GitHub hostname")
    args = parser.parse_args()

    ctx = resolve_git_context(requested_ref=args.ref, preview=args.preview)
    res = find_pr_evidence(args.jira_key, ctx, github_hostname=args.hostname, pr_number=args.pr)
    print(json.dumps(res, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
