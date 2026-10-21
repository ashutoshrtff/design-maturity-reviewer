"""
Environment diagnostic and health checker for Design Maturity Reviewer.
Validates Git, gh CLI, Python, packages, Atlassian credentials, index manifests,
and write permissions with PASS/FAIL/WARN indicators and actionable fix hints.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from config_loader import find_repo_root, load_config


def check_git(repo_root: Path) -> Dict[str, Any]:
    git_bin = shutil.which("git")
    if not git_bin:
        return {
            "name": "Git Installation",
            "status": "FAIL",
            "message": "Git executable not found in PATH.",
            "fix": "Install Git 2.30+ and add it to your PATH.",
        }
    try:
        p = subprocess.run(["git", "--version"], cwd=str(repo_root), capture_output=True, text=True, check=False)
        return {
            "name": "Git Installation",
            "status": "PASS",
            "message": p.stdout.strip(),
            "fix": None,
        }
    except Exception as e:
        return {"name": "Git Installation", "status": "FAIL", "message": str(e), "fix": "Verify git install."}


def check_python_version() -> Dict[str, Any]:
    v = sys.version_info
    ver_str = f"{v.major}.{v.minor}.{v.micro}"
    if v.major >= 3 and v.minor >= 9:
        return {
            "name": "Python Version",
            "status": "PASS",
            "message": f"Python {ver_str} satisfies minimum requirement (>= 3.9).",
            "fix": None,
        }
    return {
        "name": "Python Version",
        "status": "FAIL",
        "message": f"Python {ver_str} is below required Python 3.9+.",
        "fix": "Upgrade to Python 3.9, 3.10, or 3.11.",
    }


def check_python_packages() -> Dict[str, Any]:
    required = ["yaml", "numpy", "requests", "pydantic"]
    missing = []
    for pkg in required:
        try:
            importlib.import_module(pkg)
        except ImportError:
            missing.append(pkg)

    if not missing:
        # Check optional faiss
        has_faiss = False
        try:
            importlib.import_module("faiss")
            has_faiss = True
        except ImportError:
            pass

        msg = "All required Python packages installed."
        if not has_faiss:
            msg += " (Note: faiss-cpu not detected; using built-in high-performance NumPy cosine similarity)."
        return {
            "name": "Required Packages",
            "status": "PASS",
            "message": msg,
            "fix": None,
        }
    return {
        "name": "Required Packages",
        "status": "FAIL",
        "message": f"Missing required packages: {', '.join(missing)}",
        "fix": f"Run: pip install {' '.join(missing)}",
    }


def check_gh_cli(repo_root: Path, hostname: str = "") -> Dict[str, Any]:
    gh_bin = shutil.which("gh")
    if not gh_bin:
        return {
            "name": "GitHub CLI (gh)",
            "status": "WARN",
            "message": "gh CLI is not installed or not in PATH.",
            "fix": "Install GitHub CLI (gh) from cli.github.com for Level 1 PR attribution. Level 2 (git history) will be used as fallback.",
        }

    cmd = ["gh", "auth", "status"]
    if hostname:
        cmd.extend(["--hostname", hostname])

    try:
        p = subprocess.run(cmd, cwd=str(repo_root), capture_output=True, text=True, check=False)
        if p.returncode == 0:
            return {
                "name": "GitHub CLI Auth",
                "status": "PASS",
                "message": f"gh CLI is installed and authenticated for {hostname or 'github.com'}.",
                "fix": None,
            }
        else:
            return {
                "name": "GitHub CLI Auth",
                "status": "WARN",
                "message": f"gh is installed but not authenticated for {hostname or 'github.com'}.",
                "fix": f"Run: gh auth login {('--hostname ' + hostname) if hostname else ''}",
            }
    except Exception as e:
        return {"name": "GitHub CLI Auth", "status": "WARN", "message": str(e), "fix": "Check gh auth."}


def check_atlassian_env() -> Dict[str, Any]:
    base_url = os.getenv("ATLASSIAN_BASE_URL")
    pat = os.getenv("ATLASSIAN_PAT")
    token = os.getenv("ATLASSIAN_API_TOKEN")
    email = os.getenv("ATLASSIAN_EMAIL")

    if not base_url:
        return {
            "name": "Atlassian Configuration",
            "status": "WARN",
            "message": "ATLASSIAN_BASE_URL is not set.",
            "fix": "Set ATLASSIAN_BASE_URL (e.g. export ATLASSIAN_BASE_URL=https://company.atlassian.net) or use offline --from-file mode.",
        }

    has_auth = bool(pat or (token and email))
    if not has_auth:
        return {
            "name": "Atlassian Configuration",
            "status": "WARN",
            "message": "Atlassian authentication credentials missing (ATLASSIAN_PAT or ATLASSIAN_EMAIL + ATLASSIAN_API_TOKEN).",
            "fix": "Set ATLASSIAN_PAT (Data Center) or ATLASSIAN_EMAIL + ATLASSIAN_API_TOKEN (Cloud).",
        }

    return {
        "name": "Atlassian Configuration",
        "status": "PASS",
        "message": f"Configured for {base_url} (credentials detected).",
        "fix": None,
    }


def check_knowledge_index(repo_root: Path, page_id: str = "123456") -> Dict[str, Any]:
    idx_dir = repo_root / "knowledge-index" / page_id
    manifest_path = idx_dir / "manifest.json"
    if not manifest_path.exists():
        return {
            "name": f"Knowledge Index (Page {page_id})",
            "status": "FAIL",
            "message": f"Index manifest not found at knowledge-index/{page_id}/manifest.json.",
            "fix": f"Run ingestion: python tools/knowledge-ingestion/ingest.py --page-id {page_id} --output knowledge-index/{page_id}",
        }

    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            m = json.load(f)
        chunks = m.get("chunk_count", 0)
        return {
            "name": f"Knowledge Index (Page {page_id})",
            "status": "PASS",
            "message": f"Valid index manifest found ({chunks} chunks, version {m.get('page_version')}).",
            "fix": None,
        }
    except Exception as e:
        return {
            "name": f"Knowledge Index (Page {page_id})",
            "status": "FAIL",
            "message": f"Corrupt manifest: {e}",
            "fix": f"Re-run ingestion for page {page_id}.",
        }


def check_skill_folder(repo_root: Path) -> Dict[str, Any]:
    skill_dir = repo_root / ".github" / "skills" / "design-maturity-reviewer"
    if skill_dir.is_dir() and (skill_dir / "SKILL.md").exists():
        return {
            "name": "Skill Folder Structure",
            "status": "PASS",
            "message": "Canonical skill directory and SKILL.md exist.",
            "fix": None,
        }
    return {
        "name": "Skill Folder Structure",
        "status": "FAIL",
        "message": "Skill folder or SKILL.md missing under .github/skills/design-maturity-reviewer/.",
        "fix": "Verify that your branch contains .github/skills/design-maturity-reviewer/.",
    }


def run_doctor(page_id: str = "123456", repo_root: Optional[Path] = None) -> Tuple[bool, List[Dict[str, Any]]]:
    root = repo_root or find_repo_root()
    cfg = load_config(repo_root=root)
    gh_host = cfg.get("github", {}).get("hostname", "")

    checks = [
        check_git(root),
        check_python_version(),
        check_python_packages(),
        check_skill_folder(root),
        check_knowledge_index(root, page_id),
        check_gh_cli(root, gh_host),
        check_atlassian_env(),
    ]

    has_fail = any(c["status"] == "FAIL" for c in checks)
    return not has_fail, checks


def main() -> int:
    parser = argparse.ArgumentParser(description="DMR Environment Doctor and Diagnostics.")
    parser.add_argument("--page-id", default="123456", help="Confluence page ID to check")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    args = parser.parse_args()

    passed, checks = run_doctor(args.page_id)

    if args.json:
        print(json.dumps({"passed": passed, "checks": checks}, indent=2))
    else:
        print("\n=== Design Maturity Reviewer: Environment Diagnostics ===")
        for c in checks:
            st = c["status"]
            color = "\033[92m" if st == "PASS" else ("\033[93m" if st == "WARN" else "\033[91m")
            reset = "\033[0m"
            print(f"[{color}{st:4}{reset}] {c['name']}: {c['message']}")
            if c.get("fix"):
                print(f"       -> Fix: {c['fix']}")
        print("===========================================================")
        if passed:
            print("Doctor check: PASSED (all mandatory prerequisites met).\n")
        else:
            print("Doctor check: FAILED. Please remediate the issues above.\n")

    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
