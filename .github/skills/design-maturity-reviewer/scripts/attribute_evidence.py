"""
Evidence attribution script for Design Maturity Reviewer.
Uses git blame on explicit ref to associate code lines with commits and PRs.
In preview mode, identifies uncommitted lines as 'working tree (preview)'.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from git_context import GitContext, resolve_git_context, run_git_cmd


def get_commit_pr_association(commit_sha: str, repo_root: Path, hostname: str = "") -> Optional[int]:
    """Resolve commit to PR number via gh api or commit message parsing."""
    if not commit_sha or commit_sha.startswith("0000000"):
        return None

    # Try commit message inspection
    code, msg, _ = run_git_cmd(["log", "-1", "--pretty=format:%s%n%b", commit_sha], cwd=repo_root)
    if code == 0 and msg:
        m = re.search(r"\(#(\d+)\)|Merge pull request #(\d+)", msg)
        if m:
            return int(m.group(1) or m.group(2))

    # Try GitHub API if gh is present
    gh_cmd = ["api", f"repos/:owner/:repo/commits/{commit_sha}/pulls"]
    if hostname:
        gh_cmd.extend(["--hostname", hostname])

    try:
        proc = subprocess.run(["gh"] + gh_cmd, cwd=str(repo_root), capture_output=True, text=True, check=False)
        if proc.returncode == 0 and proc.stdout.strip():
            data = json.loads(proc.stdout)
            if isinstance(data, list) and data:
                return data[0].get("number")
    except Exception:
        pass

    return None


def attribute_line(
    file_path: str,
    line_number: int,
    context: GitContext,
    github_hostname: str = "",
) -> Dict[str, Any]:
    """Blame a single line at the context's reference."""
    repo_root = Path(context.repo_root)
    norm_path = file_path.replace("\\", "/").lstrip("/")

    # Check if working-tree uncommitted in preview mode
    if context.mode == "preview":
        disk_path = repo_root / norm_path
        if disk_path.exists():
            code, status_out, _ = run_git_cmd(["status", "--porcelain", norm_path], cwd=repo_root)
            # If untracked or modified in status
            if status_out.strip() or norm_path in context.untracked_files or norm_path in context.unstaged_files:
                return {
                    "file_path": norm_path,
                    "line_number": line_number,
                    "commit_sha": "uncommitted",
                    "pr_number": None,
                    "attribution_source": "working_tree_preview",
                    "confidence": "provisional",
                }
        else:
            return {
                "file_path": norm_path,
                "line_number": line_number,
                "commit_sha": "uncommitted",
                "pr_number": None,
                "attribution_source": "working_tree_preview",
                "confidence": "provisional",
            }

    # Run git blame on committed ref
    ref_arg = context.resolved_commit
    blame_args = ["blame", "-L", f"{line_number},{line_number}", "--porcelain", ref_arg, "--", norm_path]
    code, out, _ = run_git_cmd(blame_args, cwd=repo_root)

    if code != 0 or not out:
        return {
            "file_path": norm_path,
            "line_number": line_number,
            "commit_sha": context.resolved_commit[:8] if context.resolved_commit else "unknown",
            "pr_number": None,
            "attribution_source": "fallback_ref",
            "confidence": "low",
        }

    first_line = out.splitlines()[0]
    sha = first_line.split()[0]

    if sha.startswith("0000000"):
        return {
            "file_path": norm_path,
            "line_number": line_number,
            "commit_sha": "working-tree",
            "pr_number": None,
            "attribution_source": "working_tree_preview",
            "confidence": "provisional",
        }

    pr_num = get_commit_pr_association(sha, repo_root, github_hostname)

    return {
        "file_path": norm_path,
        "line_number": line_number,
        "commit_sha": sha[:8],
        "pr_number": pr_num,
        "attribution_source": "git_blame",
        "confidence": "high" if pr_num else "medium",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Attribute code evidence line to commit and PR.")
    parser.add_argument("--file", required=True, help="File path")
    parser.add_argument("--line", type=int, required=True, help="Line number")
    parser.add_argument("--ref", help="Target git ref")
    parser.add_argument("--preview", action="store_true", help="Preview mode")
    parser.add_argument("--hostname", default="", help="GitHub hostname")
    args = parser.parse_args()

    ctx = resolve_git_context(requested_ref=args.ref, preview=args.preview)
    res = attribute_line(args.file, args.line, ctx, github_hostname=args.hostname)
    print(json.dumps(res, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
