"""
Test helpers and mock repository setup for Design Maturity Reviewer test suite.
Constructs temporary Git repositories, commits, branches, and sample fixtures.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


SAMPLE_DESIGN_MARKDOWN = """# Instant Payment Settlement Engine
Architecture and operational requirements for real-time payment settlement.

## 1. Idempotency & Duplicate Request Protection
All incoming payment settlement requests to `/v1/settlements` must provide a unique `Idempotency-Key` HTTP header.
The engine must check if the key was previously processed:
- If key was processed within 24 hours, return HTTP 200 with the cached response and `X-Cache: HIT`.
- If key is currently being processed, return HTTP 409 Conflict with code `IDEMPOTENCY_CONCURRENT_REQUEST`.

## 2. Dynamic Transaction Fee Calculation
The settlement processor must calculate transaction fees according to tier rules:
- Tier 1 (< $1,000): 0.5% + $0.10 flat fee.
- Tier 2 ($1,000 - $10,000): 0.35% + $0.25 flat fee.
- Tier 3 (> $10,000): 0.20% flat fee.
Fee calculation must be logged with field `calculated_fee_cents`.

## 3. High Availability Multi-AZ Failover
Database failover must switch to secondary replica across AWS Availability Zones in under 500ms without data loss.

## 4. End-of-Day Audit Log Archival
Settlement audit records older than 30 days must be automatically compressed and uploaded to AWS S3 bucket `settlement-audit-archive`.

## 5. Performance and Latency
System performance must feel suitably snappy and scalable under peak holiday loads.
"""

SAMPLE_JIRA_PAY123 = {
    "key": "PAY-123",
    "summary": "Implement Idempotency and Deduplication for Settlement API",
    "description": (
        "Implement idempotency verification on /v1/settlements to prevent double charges.\n\n"
        "h3. Acceptance Criteria\n"
        "- [x] Validate presence of Idempotency-Key header on POST /v1/settlements\n"
        "- [ ] Return HTTP 409 Conflict with error code IDEMPOTENCY_CONCURRENT_REQUEST if concurrent\n"
        "- [x] Cache successful response payload for 24 hours and set X-Cache: HIT\n"
        "\n"
        "h3. Additional Requirements\n"
        "- Support export of settlement ledger to Excel spreadsheet format (.xlsx)\n"
    ),
    "status": "In Progress",
    "components": ["Settlement-Core", "API-Gateway"],
    "labels": ["payments", "p0", "reliability"],
    "linked_issues": ["PAY-100", "PAY-105"],
}


class TempGitRepo:
    """Manages an isolated temporary git repository with simulated commits and branches."""

    def __init__(self) -> None:
        self.temp_dir = tempfile.mkdtemp(prefix="dmr_test_repo_")
        self.path = Path(self.temp_dir).resolve()
        self.init_repo()

    def run_git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        cmd = ["git"] + list(args)
        return subprocess.run(
            cmd,
            cwd=str(self.path),
            capture_output=True,
            text=True,
            check=check,
        )

    def init_repo(self) -> None:
        self.run_git("init", "-b", "main")
        self.run_git("config", "user.name", "Test Reviewer")
        self.run_git("config", "user.email", "reviewer@example.com")
        self.run_git("config", "commit.gpgsign", "false")

        # Initial commit on main
        readme = self.path / "README.md"
        readme.write_text("# Payment Settlement Core\n", encoding="utf-8")
        self.run_git("add", "README.md")
        self.run_git("commit", "-m", "Initial commit")

        # Create origin remote pointing to a bare clone to simulate origin/main
        origin_dir = tempfile.mkdtemp(prefix="dmr_test_origin_")
        self.origin_path = Path(origin_dir).resolve()
        subprocess.run(["git", "clone", "--bare", str(self.path), str(self.origin_path)], check=True, capture_output=True)
        self.run_git("remote", "add", "origin", str(self.origin_path))
        self.run_git("fetch", "origin")
        self.run_git("branch", "--set-upstream-to=origin/main", "main")

    def create_file(self, rel_path: str, content: str) -> Path:
        f = self.path / rel_path
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(content, encoding="utf-8")
        return f

    def commit_file(self, rel_path: str, content: str, message: str) -> str:
        self.create_file(rel_path, content)
        self.run_git("add", rel_path)
        self.run_git("commit", "-m", message)
        sha = self.run_git("rev-parse", "HEAD").stdout.strip()
        return sha

    def push_to_origin(self, branch: str = "main") -> None:
        self.run_git("push", "origin", branch)

    def cleanup(self) -> None:
        if hasattr(self, "temp_dir") and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        if hasattr(self, "origin_path") and os.path.exists(self.origin_path):
            shutil.rmtree(self.origin_path, ignore_errors=True)
