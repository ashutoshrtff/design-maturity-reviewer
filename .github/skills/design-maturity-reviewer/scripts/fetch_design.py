"""
Design document fetcher for DMR.
Retrieves Confluence design pages and children, with offline file fallback.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


def fetch_design_from_file(file_path: Path, page_id: str = "123456", version: int = 12) -> Dict[str, Any]:
    """Load design doc from local markdown/text file."""
    text = file_path.read_text(encoding="utf-8", errors="replace")
    content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()

    # Extract title from first # heading if available
    title = f"Design Document {page_id}"
    for line in text.splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
            break

    return {
        "page_id": page_id,
        "title": title,
        "version": version,
        "content_hash": content_hash,
        "content": text,
        "children": [],
        "source": "file",
    }


def fetch_design_from_confluence(
    page_id: str,
    base_url: str,
    auth_headers: Dict[str, str],
    max_depth: int = 3,
) -> Dict[str, Any]:
    """Fetch design page and children from Confluence REST API."""
    import requests

    endpoint = f"{base_url.rstrip('/')}/rest/api/content/{page_id}?expand=body.storage,version,title"
    res = requests.get(endpoint, headers=auth_headers, timeout=15)
    if res.status_code != 200:
        raise RuntimeError(f"Failed to fetch Confluence page {page_id}: HTTP {res.status_code} {res.text[:200]}")

    data = res.json()
    title = data.get("title", f"Confluence {page_id}")
    ver_info = data.get("version", {})
    version = ver_info.get("number", 1)
    body_storage = data.get("body", {}).get("storage", {}).get("value", "")

    # Clean HTML/storage format to text/markdown representation
    content_hash = hashlib.sha256(body_storage.encode("utf-8")).hexdigest()

    # Children
    children: List[Dict[str, Any]] = []
    if max_depth > 0:
        child_endpoint = f"{base_url.rstrip('/')}/rest/api/content/{page_id}/child/page"
        c_res = requests.get(child_endpoint, headers=auth_headers, timeout=15)
        if c_res.status_code == 200:
            c_data = c_res.json()
            for item in c_data.get("results", []):
                children.append(
                    {
                        "page_id": item.get("id"),
                        "title": item.get("title"),
                        "version": item.get("version", {}).get("number", 1),
                    }
                )

    return {
        "page_id": page_id,
        "title": title,
        "version": version,
        "content_hash": content_hash,
        "content": body_storage,
        "children": children,
        "source": "confluence_api",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch Confluence design content.")
    parser.add_argument("--page-id", required=True, help="Confluence page ID")
    parser.add_argument("--from-file", help="Path to local design markdown/text file")
    parser.add_argument("--version", type=int, default=12, help="Design version")
    args = parser.parse_args()

    if args.from_file:
        doc = fetch_design_from_file(Path(args.from_file), args.page_id, args.version)
        print(json.dumps(doc, indent=2))
        return 0

    base_url = os.getenv("ATLASSIAN_BASE_URL", "")
    token = os.getenv("ATLASSIAN_API_TOKEN") or os.getenv("ATLASSIAN_PAT", "")
    email = os.getenv("ATLASSIAN_EMAIL", "")

    if not base_url or not token:
        # If no creds, inform clearly
        sys.stderr.write(
            "Error: ATLASSIAN_BASE_URL and credentials not configured. Use --from-file for offline operations.\n"
        )
        return 1

    headers = {"Accept": "application/json"}
    if email:
        import base64

        auth_str = base64.b64encode(f"{email}:{token}".encode("utf-8")).decode("utf-8")
        headers["Authorization"] = f"Basic {auth_str}"
    else:
        headers["Authorization"] = f"Bearer {token}"

    try:
        doc = fetch_design_from_confluence(args.page_id, base_url, headers)
        print(json.dumps(doc, indent=2))
        return 0
    except Exception as e:
        sys.stderr.write(f"Confluence fetch error: {e}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
