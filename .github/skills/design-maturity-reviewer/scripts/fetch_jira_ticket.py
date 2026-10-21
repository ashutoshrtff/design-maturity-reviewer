"""
Jira ticket fetcher and acceptance criteria parser for DMR.
Supports Jira Cloud, Jira Data Center, and offline fixture files.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


def parse_acceptance_criteria(text: str) -> List[str]:
    """
    Conservatively parse acceptance criteria from ticket description:
    - Checklists: - [ ] or - [x] or * [ ]
    - Gherkin blocks: Scenario: / Given / When / Then
    - Numbered or bulleted items under 'Acceptance Criteria' or 'AC' headings
    """
    if not text:
        return []

    criteria: List[str] = []
    lines = text.splitlines()
    in_ac_section = False

    ac_heading_re = re.compile(r"(?:h\d+\.|\#{1,6}|(?:\*\*))?\s*(?:acceptance\s*criteria|ac)\b", re.IGNORECASE)
    checkbox_re = re.compile(r"^\s*[-*]\s*\[([ xX])\]\s*(.+)$")
    bullet_re = re.compile(r"^\s*[-*#]\s*(.+)$")
    numbered_re = re.compile(r"^\s*\d+[\.)]\s*(.+)$")

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        if ac_heading_re.search(stripped):
            in_ac_section = True
            continue

        # If we hit another major heading (h1, h2, ##), exit AC section
        if in_ac_section and re.match(r"^(?:h[1-2]\.|\#{1,2}\s|[A-Z][\w\s]{2,20}:)", stripped) and not ac_heading_re.search(stripped):
            in_ac_section = False

        # Direct checkbox match anywhere in description
        cb_match = checkbox_re.match(line)
        if cb_match:
            desc = cb_match.group(2).strip()
            checked = cb_match.group(1).lower() == "x"
            prefix = "[DONE] " if checked else ""
            criteria.append(f"{prefix}{desc}")
            continue

        # Direct Gherkin match anywhere in description
        if any(stripped.startswith(k) for k in ("Given ", "When ", "Then ", "Scenario:")):
            criteria.append(stripped)
            continue

        # Bullets or numbers inside AC section
        if in_ac_section:
            b_match = bullet_re.match(line) or numbered_re.match(line)
            if b_match:
                criteria.append(b_match.group(1).strip())
            elif stripped.startswith("Given ") or stripped.startswith("When ") or stripped.startswith("Then ") or stripped.startswith("Scenario:"):
                criteria.append(stripped)

    # De-duplicate while preserving order
    seen = set()
    deduped = []
    for c in criteria:
        if c not in seen:
            seen.add(c)
            deduped.append(c)

    return deduped


def fetch_from_file(file_path: Path) -> Dict[str, Any]:
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # If raw Jira API response
    if "fields" in data:
        fields = data.get("fields", {})
        desc = fields.get("description", "")
        if isinstance(desc, dict):
            # Atlassian Document Format (ADF) handling: extract plain text
            desc = json.dumps(desc)
        ac = parse_acceptance_criteria(desc)
        return {
            "key": data.get("key", "UNKNOWN"),
            "summary": fields.get("summary", ""),
            "description": desc,
            "acceptance_criteria": ac,
            "status": fields.get("status", {}).get("name", "Unknown"),
            "components": [c.get("name") for c in fields.get("components", [])],
            "labels": fields.get("labels", []),
            "linked_issues": [
                link.get("outwardIssue", {}).get("key") or link.get("inwardIssue", {}).get("key")
                for link in fields.get("issuelinks", [])
                if link.get("outwardIssue") or link.get("inwardIssue")
            ],
            "source": "file",
        }

    # Already normalized fixture format
    desc = data.get("description", "")
    ac = data.get("acceptance_criteria") or parse_acceptance_criteria(desc)
    data["acceptance_criteria"] = ac
    data["source"] = "file"
    return data


def fetch_from_jira_api(
    ticket_key: str,
    base_url: str,
    email: str = "",
    token: str = "",
    deployment_type: str = "auto",
) -> Dict[str, Any]:
    import requests

    endpoint = f"{base_url.rstrip('/')}/rest/api/2/issue/{ticket_key}"
    headers = {"Accept": "application/json"}

    # Determine auth
    is_cloud = (deployment_type == "cloud") or ("atlassian.net" in base_url)
    if is_cloud and email:
        auth_pair = f"{email}:{token}"
        encoded = base64.b64encode(auth_pair.encode("utf-8")).decode("utf-8")
        headers["Authorization"] = f"Basic {encoded}"
    else:
        headers["Authorization"] = f"Bearer {token}"

    res = requests.get(endpoint, headers=headers, timeout=15)
    if res.status_code != 200:
        raise RuntimeError(f"Jira API error for {ticket_key}: HTTP {res.status_code} {res.text[:200]}")

    data = res.json()
    return fetch_from_file_data(data)


def fetch_from_file_data(data: Dict[str, Any]) -> Dict[str, Any]:
    fields = data.get("fields", {})
    desc = fields.get("description") or ""
    ac = parse_acceptance_criteria(desc)
    return {
        "key": data.get("key", ""),
        "summary": fields.get("summary", ""),
        "description": desc,
        "acceptance_criteria": ac,
        "status": fields.get("status", {}).get("name", "Unknown"),
        "components": [c.get("name") for c in fields.get("components", [])],
        "labels": fields.get("labels", []),
        "linked_issues": [
            link.get("outwardIssue", {}).get("key") or link.get("inwardIssue", {}).get("key")
            for link in fields.get("issuelinks", [])
            if link.get("outwardIssue") or link.get("inwardIssue")
        ],
        "source": "jira_api",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch Jira ticket details.")
    parser.add_argument("--key", required=True, help="Jira ticket key (e.g. PAY-123)")
    parser.add_argument("--from-file", help="Path to local fixture JSON file")
    args = parser.parse_args()

    if args.from_file:
        res = fetch_from_file(Path(args.from_file))
        print(json.dumps(res, indent=2))
        return 0

    base_url = os.getenv("ATLASSIAN_BASE_URL", "")
    token = os.getenv("ATLASSIAN_API_TOKEN") or os.getenv("ATLASSIAN_PAT", "")
    email = os.getenv("ATLASSIAN_EMAIL", "")

    if not base_url or not token:
        sys.stderr.write("Error: ATLASSIAN_BASE_URL and credentials not set. Use --from-file for offline testing.\n")
        return 1

    try:
        res = fetch_from_jira_api(args.key, base_url, email=email, token=token)
        print(json.dumps(res, indent=2))
        return 0
    except Exception as e:
        sys.stderr.write(f"Fetch error: {e}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
