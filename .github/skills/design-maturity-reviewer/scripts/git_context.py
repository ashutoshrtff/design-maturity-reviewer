"""
Git reference resolution and code context for Design Maturity Reviewer.
Handles origin/main baseline, branch refs, PR head resolution, and working tree preview.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class GitContext:
    repo_root: str
    requested_ref: str
    resolved_commit: str
    base_ref: str
    mode: str  # "verified" or "preview"
    current_branch: str
    is_dirty: bool
    ahead_count: int
    behind_count: int
    untracked_files: List[str]
    staged_files: List[str]
    unstaged_files: List[str]


def run_git_cmd(args: List[str], cwd: Optional[Path] = None) -> Tuple[int, str, str]:
    """Execute git command safely without shell string interpolation."""
    try:
        proc = subprocess.run(
            ["git"] + args,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            check=False,
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except Exception as e:
        return 1, "", str(e)


def get_repo_root(cwd: Optional[Path] = None) -> Path:
    code, out, _ = run_git_cmd(["rev-parse", "--show-toplevel"], cwd=cwd)
    if code == 0 and out:
        return Path(out).resolve()
    return Path.cwd().resolve()


def get_current_branch(repo_root: Path) -> str:
    code, out, _ = run_git_cmd(["rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_root)
    if code == 0 and out:
        return out
    return "HEAD"


def get_commit_sha(ref: str, repo_root: Path) -> str:
    code, out, _ = run_git_cmd(["rev-parse", ref], cwd=repo_root)
    if code == 0 and out:
        return out
    return ""


def get_working_tree_status(repo_root: Path) -> Tuple[bool, List[str], List[str], List[str]]:
    """Return (is_dirty, staged_files, unstaged_files, untracked_files)."""
    code, out, _ = run_git_cmd(["status", "--porcelain"], cwd=repo_root)
    if code != 0 or not out:
        return False, [], [], []

    staged: List[str] = []
    unstaged: List[str] = []
    untracked: List[str] = []

    for line in out.splitlines():
        if len(line) < 3:
            continue
        index_status = line[0]
        work_status = line[1]
        file_path = line[3:].strip()

        if index_status == "?" and work_status == "?":
            untracked.append(file_path)
        else:
            if index_status not in (" ", "?"):
                staged.append(file_path)
            if work_status not in (" ", "?"):
                unstaged.append(file_path)

    is_dirty = bool(staged or unstaged or untracked)
    return is_dirty, staged, unstaged, untracked


def check_ancestry(base_ref: str, head_ref: str, repo_root: Path) -> Tuple[int, int]:
    """Check ahead and behind counts between base and head using rev-list."""
    code, out, _ = run_git_cmd(["rev-list", "--left-right", "--count", f"{base_ref}...{head_ref}"], cwd=repo_root)
    if code == 0 and out:
        parts = out.split()
        if len(parts) == 2:
            try:
                behind = int(parts[0])
                ahead = int(parts[1])
                return ahead, behind
            except ValueError:
                pass
    return 0, 0


def resolve_git_context(
    requested_ref: Optional[str] = None,
    preview: bool = False,
    pr_number: Optional[int] = None,
    main_branch: str = "main",
    no_fetch: bool = True,
    repo_root: Optional[Path] = None,
    github_hostname: str = "",
) -> GitContext:
    root = repo_root or get_repo_root()
    curr_branch = get_current_branch(root)
    is_dirty, staged, unstaged, untracked = get_working_tree_status(root)

    base_ref = f"origin/{main_branch}"

    # If fetch is requested and remotes exist, attempt fetch
    if not no_fetch:
        run_git_cmd(["fetch", "origin", main_branch], cwd=root)

    # PR mode
    if pr_number is not None:
        mode = "preview"  # PR head is provisional until merged
        # Try resolving PR commit via gh if available
        gh_args = ["pr", "view", str(pr_number), "--json", "headRefOid,headRefName"]
        if github_hostname:
            gh_args.extend(["--hostname", github_hostname])
        try:
            p = subprocess.run(["gh"] + gh_args, cwd=str(root), capture_output=True, text=True, check=False)
            if p.returncode == 0 and p.stdout:
                data = json.loads(p.stdout)
                target_ref = data.get("headRefOid", f"refs/pull/{pr_number}/head")
                sha = data.get("headRefOid") or get_commit_sha(target_ref, root)
                return GitContext(
                    repo_root=str(root),
                    requested_ref=f"PR #{pr_number}",
                    resolved_commit=sha or f"pr-{pr_number}-head",
                    base_ref=base_ref,
                    mode=mode,
                    current_branch=data.get("headRefName", f"pr-{pr_number}"),
                    is_dirty=False,
                    ahead_count=0,
                    behind_count=0,
                    untracked_files=[],
                    staged_files=[],
                    unstaged_files=[],
                )
        except Exception:
            pass

    # Preview mode
    if preview or requested_ref in ("HEAD", "working-tree", "preview"):
        mode = "preview"
        req_ref = "HEAD (preview / working tree)"
        commit_sha = get_commit_sha("HEAD", root)
        ahead, behind = check_ancestry(base_ref, "HEAD", root)
        return GitContext(
            repo_root=str(root),
            requested_ref=req_ref,
            resolved_commit=commit_sha or "working-tree",
            base_ref=base_ref,
            mode=mode,
            current_branch=curr_branch,
            is_dirty=is_dirty,
            ahead_count=ahead,
            behind_count=behind,
            untracked_files=untracked,
            staged_files=staged,
            unstaged_files=unstaged,
        )

    # Default baseline / verified ref
    req_ref = requested_ref or base_ref
    mode = "verified" if req_ref in (base_ref, "main", f"refs/remotes/{base_ref}") else "branch"
    commit_sha = get_commit_sha(req_ref, root)

    # If requested ref doesn't resolve (e.g. origin/main before remote configured), fallback to HEAD
    if not commit_sha:
        commit_sha = get_commit_sha("HEAD", root)
        req_ref = "HEAD"
        mode = "verified"

    ahead, behind = check_ancestry(base_ref, req_ref, root)

    return GitContext(
        repo_root=str(root),
        requested_ref=req_ref,
        resolved_commit=commit_sha,
        base_ref=base_ref,
        mode=mode,
        current_branch=curr_branch,
        is_dirty=is_dirty,
        ahead_count=ahead,
        behind_count=behind,
        untracked_files=untracked,
        staged_files=staged,
        unstaged_files=unstaged,
    )


def read_file_content(file_path: str, context: GitContext) -> Optional[str]:
    """
    Read file content at the context's ref.
    If context.mode == 'preview', reads the working tree (including uncommitted changes).
    Otherwise, reads committed object via git show <ref>:<path>.
    """
    root = Path(context.repo_root)
    norm_path = file_path.replace("\\", "/").lstrip("/")

    if context.mode == "preview":
        disk_path = root / norm_path
        if disk_path.is_file():
            try:
                return disk_path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                return None
        return None

    # Read from git ref
    code, out, _ = run_git_cmd(["show", f"{context.resolved_commit}:{norm_path}"], cwd=root)
    if code == 0:
        return out
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve Git context for DMR.")
    parser.add_argument("--ref", help="Target Git reference (default: origin/main)")
    parser.add_argument("--preview", action="store_true", help="Inspect current branch including uncommitted changes")
    parser.add_argument("--pr", type=int, help="PR number to resolve")
    parser.add_argument("--no-fetch", action="store_true", default=True, help="Skip git fetch")
    args = parser.parse_args()

    ctx = resolve_git_context(
        requested_ref=args.ref,
        preview=args.preview,
        pr_number=args.pr,
        no_fetch=args.no_fetch,
    )
    print(json.dumps(asdict(ctx), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
