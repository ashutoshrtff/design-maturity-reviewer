# Git Reference Resolution & Preview Semantics

## Reference Types

### 1. Authoritative Baseline (`origin/main`)
- Default for all code verification.
- DMR fetches `origin/<main_branch>` (skippable via `--no-fetch` for offline environments) and inspects code via `git show <sha>:<path>` and `git grep <sha>`.
- Does NOT depend on what branch the engineer currently has checked out.

### 2. Preview Mode (`--preview` or `--ref HEAD`)
- Audits the engineer's active working tree (staged changes, unstaged modifications, and untracked source files).
- Answers: *"Does my local implementation complete ticket PAY-123 before I submit or merge my PR?"*
- Always labelled with `PREVIEW (PROVISIONAL)` banner.
- Evidence from preview runs is excluded from authoritative baseline coverage numbers.

### 3. PR Mode (`--pr <number>`)
- Resolves the PR head commit via `gh pr view <number> --json headRefOid`.
- Audits the PR head commit directly.

### 4. Behind-Origin Checks
- `preflight_index_check.py` checks `git diff --stat origin/main -- knowledge-index design-status`.
- If the feature branch is behind main in baseline mode, stops to prevent stale rollups.
