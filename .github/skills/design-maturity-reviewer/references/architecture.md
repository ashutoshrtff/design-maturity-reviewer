# DMR Architecture & Execution Boundaries

## Overview
The Design Maturity Reviewer (DMR) is an independent, evidence-based assessment system that audits source code against Confluence design requirements across distributed PRs and Jira tickets.

```
                           +---------------------------+
                           |   Confluence Design Doc   |
                           +-------------+-------------+
                                         |
                                         v
                           +---------------------------+
                           | tools/knowledge-ingestion |
                           |   (Heading Chunk + FAISS) |
                           +-------------+-------------+
                                         |
                                         v
                           +---------------------------+
                           |   knowledge-index/<id>    |
                           +-------------+-------------+
                                         |
               +-------------------------+-------------------------+
               |                                                   |
               v                                                   v
     [ Mode A: Ticket Review ]                           [ Mode B: Design Baseline ]
   (Jira Key + Ref/Preview)                                (origin/main Baseline)
               |                                                   |
               v                                                   v
   +-----------------------+                             +-----------------------+
   | fetch_jira_ticket.py  |                             | query_design_context  |
   | query_design_context  |                             | extract_requirements  |
   | search_code_evidence  |                             | search_code_evidence  |
   | find_pr_evidence      |                             | attribute_evidence    |
   | attribute_evidence    |                             | validate_report.py    |
   | validate_report.py    |                             | ledger.py             |
   | render_report.py      |                             +-----------+-----------+
   +-----------+-----------+                                         |
               |                                                     v
               v                                         +-----------------------+
   +-----------------------+                             |       rollup.py       |
   | design-status/<id>/   |                             | (Deterministic Hashing|
   | tickets/<KEY>.md      |                             |   Promotes Merged)    |
   +-----------------------+                             +-----------+-----------+
                                                                     |
                                                                     v
                                                         +-----------------------+
                                                         |  design-status/<id>/  |
                                                         |      COVERAGE.md      |
                                                         +-----------------------+
```

## System Boundaries
- **Code Repository is Read-Only**: DMR only reads code via `git show`, `git grep`, and `git blame` at explicit Git refs. It never alters source files.
- **Artefacts**: All generated state lives under `design-status/<pageId>/` (runs, tickets, coverage).
- **Decoupled Ingestion**: Ingestion is a single-owner or CI prerequisite, never executed inside per-ticket reviews.
- **Anti-Hallucination Gate**: `validate_report.py` strictly verifies citations, line bounds, and file contents before any report is written.
