# Report Contract & Schema Specifications

## Output View 1: Ticket Coverage Report
Path: `design-status/<pageId>/tickets/<JIRA-KEY>.md`
- Header: Jira key, summary, design page, version, index date, ref, commit, mode, PR attribution method.
- PREVIEW banner (if preview mode).
- Maturity summary table with one-line verdict.
- In-scope requirement table.
- Incomplete implementation details (gaps, missing ACs).
- Ticket items with no design basis (scope creep).
- Outside-scope items with latest known statuses (informational, not re-verified).
- Low relevance and staleness warnings.

## Output View 2: Design Baseline Coverage
Path: `design-status/<pageId>/COVERAGE.md`
- Authoritative baseline ref and commit.
- Implemented coverage percentage: `Implemented / Total Applicable * 100`.
- Baseline requirements ledger table.
- Implementation gaps & unclaimed scope.
- Provisional (not on origin/main yet).
- Run disagreements and not-yet-assessed items.
