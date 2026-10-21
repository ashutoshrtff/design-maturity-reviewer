"""
Configuration loader and validator for Design Maturity Reviewer.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


def find_repo_root(start_path: Optional[Path] = None) -> Path:
    """Find the root of the git repository or fallback to current directory."""
    curr = (start_path or Path.cwd()).resolve()
    for parent in [curr] + list(curr.parents):
        if (parent / ".git").exists():
            return parent
    return curr


def get_default_config_path(repo_root: Optional[Path] = None) -> Path:
    root = repo_root or find_repo_root()
    skill_config = root / ".github" / "skills" / "design-maturity-reviewer" / "config" / "dmr.config.yml"
    if skill_config.exists():
        return skill_config
    root_config = root / "dmr.config.yml"
    if root_config.exists():
        return root_config
    example_config = root / ".github" / "skills" / "design-maturity-reviewer" / "config" / "dmr.config.example.yml"
    if example_config.exists():
        return example_config
    return root / "dmr.config.example.yml"


def load_config(config_path: Optional[str | Path] = None, repo_root: Optional[Path] = None) -> Dict[str, Any]:
    """Load and validate DMR YAML configuration."""
    root = repo_root or find_repo_root()
    path = Path(config_path) if config_path else get_default_config_path(root)

    if not path.is_absolute():
        path = (root / path).resolve()

    if not path.exists():
        # Return sensible defaults
        return {
            "_config_path": str(path),
            "_repo_root": str(root),
            "design_pages": [{"page_id": "123456"}],
            "design_context": {"top_k": 8, "max_chars_per_chunk": 1200, "min_relevance": 0.35},
            "knowledge": {
                "index_dir": "knowledge-index",
                "ingestion_command": "python tools/knowledge-ingestion/ingest.py --page-id {page_id} --output knowledge-index/{page_id}",
            },
            "atlassian": {
                "base_url_env": "ATLASSIAN_BASE_URL",
                "deployment_type": "auto",
                "email_env": "ATLASSIAN_EMAIL",
                "api_token_env": "ATLASSIAN_API_TOKEN",
                "pat_env": "ATLASSIAN_PAT",
            },
            "github": {"hostname": ""},
            "code": {"main_branch": "main", "default_ref": "origin/main", "search_paths": ["src", "app", "."]},
            "status_dir": "design-status",
        }

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    # Validate essential keys and set defaults
    data["_config_path"] = str(path)
    data["_repo_root"] = str(root)

    if "design_pages" not in data or not data["design_pages"]:
        data["design_pages"] = []

    design_context = data.setdefault("design_context", {})
    design_context.setdefault("top_k", 8)
    design_context.setdefault("max_chars_per_chunk", 1200)
    design_context.setdefault("min_relevance", 0.35)

    knowledge = data.setdefault("knowledge", {})
    knowledge.setdefault("index_dir", "knowledge-index")
    knowledge.setdefault(
        "ingestion_command",
        "python tools/knowledge-ingestion/ingest.py --page-id {page_id} --output knowledge-index/{page_id}",
    )

    atlassian = data.setdefault("atlassian", {})
    atlassian.setdefault("base_url_env", "ATLASSIAN_BASE_URL")
    atlassian.setdefault("deployment_type", "auto")
    atlassian.setdefault("email_env", "ATLASSIAN_EMAIL")
    atlassian.setdefault("api_token_env", "ATLASSIAN_API_TOKEN")
    atlassian.setdefault("pat_env", "ATLASSIAN_PAT")

    github = data.setdefault("github", {})
    github.setdefault("hostname", "")

    code = data.setdefault("code", {})
    code.setdefault("main_branch", "main")
    code.setdefault("default_ref", "origin/main")
    code.setdefault("search_paths", ["src", "app", "."])

    data.setdefault("status_dir", "design-status")

    return data


def main() -> int:
    parser = argparse.ArgumentParser(description="Load and validate DMR configuration.")
    parser.add_argument("--config", help="Path to dmr.config.yml")
    args = parser.parse_args()

    cfg = load_config(args.config)
    print(json.dumps(cfg, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
