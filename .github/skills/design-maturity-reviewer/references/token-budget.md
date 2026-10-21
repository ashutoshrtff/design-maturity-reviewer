# Token & Performance Budget Guidelines

## Principles
1. **Never dump full repositories or entire files into LLM context**:
   - `search_code_evidence.py` captures bounded snippets (±3 lines).
   - `query_design_context.py` caps chunks at `max_chars_per_chunk` (default 1200 chars).
2. **Deterministic Rollup**:
   - `rollup.py` executes 100% deterministically using Python hashing and Git plumbing without any LLM calls.
3. **Table Caps**:
   - Rendered Markdown tables display up to ~25 in-scope rows. For massive design docs, summarize aggregate counts and link to `design-status/<pageId>/requirements.json`.
4. **Re-verification Economy**:
   - Re-verify only new, changed, Partial, Pending, or stale requirements. Reuse previously valid assessments from the ledger for unchanged requirements.
