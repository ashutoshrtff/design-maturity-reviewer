# Code Evidence Rules & Revalidation

## Evidence Model
Every evidence item captured by `search_code_evidence.py` adheres to:
```json
{
  "file_path": "src/settlement/handler.py",
  "line_number": 42,
  "start_line": 39,
  "end_line": 45,
  "snippet": "if not idempotency_key:\n    raise HTTPException(status_code=400, detail=\"Missing Idempotency-Key\")",
  "snippet_hash": "a8f3b...",
  "commit_sha": "f1a2b3c4",
  "pr_number": 123,
  "attribution_source": "git_blame"
}
```

## Valid-Evidence Rule & Relocation Handling
Code refactors and squash merges frequently change line numbers and commit hashes. DMR employs content-based revalidation:
1. **Line Matching**: Check if the cited line in `origin/main` contains the normalized snippet.
2. **Relocation Scan**: If the line moved (e.g. from line 42 to line 65 due to preceding imports), scan the file for the matching snippet, update the line number, and maintain valid status.
3. **Squash Merges**: A squash merge creates a new commit SHA on main. DMR revalidates by snippet hash rather than commit ancestry, automatically promoting merged evidence.
4. **Provisional Isolation**: Evidence on unmerged branches or working trees that does not yet exist on `origin/main` is quarantined under `Provisional (not on main yet)` in `COVERAGE.md`.
