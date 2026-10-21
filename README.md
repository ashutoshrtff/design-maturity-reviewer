# Design Maturity Reviewer (DMR)

> **PSP Enterprise Engineering Hackathon 2026**  
> *Reusable GitHub Copilot Agent Skill & Automated Completeness Reviewer*

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Copilot Agent Skill](https://img.shields.io/badge/GitHub-Copilot%20Agent%20Skill-purple.svg)](#github-copilot-agent-and-skill-integration)

A PR shows what was built, not whether the **right thing** was built. Features are documented across Confluence design specifications and delivered across many pull requests and Jira tickets. 

While existing AI bots review code syntax and style, the **Design Maturity Reviewer (DMR)** assesses **implementation completeness against the design**, providing auditable, evidence-backed coverage without modifying application code.

---

## Table of Contents
- [1. Core Principles](#1-core-principles)
- [2. Architecture & Data Flow](#2-architecture--data-flow)
- [3. Five-Minute Setup](#3-five-minute-setup)
- [4. Environment Diagnostics (`doctor.py`)](#4-environment-diagnostics-doctorpy)
- [5. Operating Modes](#5-operating-modes)
  - [Mode A: Ticket Review (View 1)](#mode-a-ticket-review-view-1)
  - [Mode B: Design Baseline Coverage (View 2)](#mode-b-design-baseline-coverage-view-2)
  - [Preview Mode (`--preview`)](#preview-mode---preview)
  - [PR Mode (`--pr <number>`)](#pr-mode---pr-number)
- [6. Status & Evidence Rules](#6-status--evidence-rules)
- [7. Anti-Hallucination Gate (`validate_report.py`)](#7-anti-hallucination-gate-validate_reportpy)
- [8. Deterministic Rollup & Squash Merge Revalidation](#8-deterministic-rollup--squash-merge-revalidation)
- [9. Repository Structure](#9-repository-structure)
- [10. Copilot Integration (Agent & Prompts)](#10-copilot-integration-agent--prompts)
- [11. Running Tests](#11-running-tests)
- [12. CI/CD Automation (GitHub Actions)](#12-cicd-automation-github-actions)
- [13. Reusability & Multi-Team Adoption](#13-reusability--multi-team-adoption)

---

## 1. Core Principles

1. **Status comes solely from verifiable code evidence**: A Jira ticket in "Done" state or a merged PR does not prove implementation. Status is determined by code evidence (file, line range, bounded snippet, normalized hash).
2. **Status and Ownership are Separate**: 
   - *Status* = what the code proves.
   - *Ownership* = which reviewed ticket claims the requirement.
   - A requirement can be implemented even if no reviewed ticket claims it.
3. **PRs are for Attribution Only**: Commits and PRs identify who delivered code, never whether it satisfies the design.
4. **Ref-Aware Inspection**: DMR never assumes the developer has `main` checked out. All reads go through explicit Git references (`origin/main`, branch SHAs, or working tree snapshots).
5. **Read-Only Codebase**: DMR never commits application code or pushes branches. All generated artifacts are written strictly under `design-status/<pageId>/`.

---

## 2. Architecture & Data Flow

```
                     +-------------------------------+
                     | Confluence Design Page & Tree |
                     +---------------+---------------+
                                     |
                                     v
                     +-------------------------------+
                     |   tools/knowledge-ingestion   |
                     | (Heading Chunker + Embedding) |
                     +---------------+---------------+
                                     |
                                     v
                     +-------------------------------+
                     |     knowledge-index/<id>/     |
                     |  manifest.json & chunks.json  |
                     +---------------+---------------+
                                     |
          +--------------------------+--------------------------+
          |                                                     |
          v                                                     v
 [ Mode A: Ticket Mode ]                              [ Mode B: Design Baseline ]
(Jira Key + Ref / Preview)                              (origin/main Whole Repo)
          |                                                     |
          v                                                     v
+------------------------+                            +-------------------------+
|  fetch_jira_ticket.py  |                            |  extract_requirements  |
|  query_design_context  |                            |  search_code_evidence   |
|  search_code_evidence  |                            |   attribute_evidence    |
|   find_pr_evidence     |                            |   validate_report.py    |
|  attribute_evidence    |                            |       ledger.py         |
|   validate_report.py   |                            +------------+------------+
|    render_report.py    |                                         |
+-----------+------------+                                         v
            |                                         +-------------------------+
            v                                         |        rollup.py        |
+------------------------+                            | (Deterministic Hashing, |
|  design-status/<id>/   |                            |  Promotes Squash Merges)|
|   tickets/<KEY>.md     |                            +------------+------------+
+------------------------+                                         |
                                                                   v
                                                      +-------------------------+
                                                      |   design-status/<id>/   |
                                                      |       COVERAGE.md       |
                                                      +-------------------------+
```

---

## 3. Five-Minute Setup

### Prerequisites
- Python 3.9+ (`python --version`)
- Git 2.30+ (`git --version`)
- Optional: GitHub CLI (`gh auth status`) for Level 1 PR queries.

### Step-by-Step
```bash
# 1. Clone or merge skill to your repository
git clone <your-repo>
cd <your-repo>

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure credentials in your shell (or use offline fixture mode)
export ATLASSIAN_BASE_URL="https://yourcompany.atlassian.net"
export ATLASSIAN_EMAIL="you@company.com"
export ATLASSIAN_API_TOKEN="your-api-token"
# For Jira Data Center / On-Prem:
# export ATLASSIAN_PAT="your-personal-access-token"

# 4. Ingest Confluence Design Page
python tools/knowledge-ingestion/ingest.py \
  --page-id 123456 \
  --output knowledge-index/123456 \
  --title "Instant Payment Settlement Engine" \
  --version 12

# 5. Run Environment Diagnostics
python .github/skills/design-maturity-reviewer/scripts/doctor.py --page-id 123456
```

---

## 4. Environment Diagnostics (`doctor.py`)

Run `doctor.py` to verify your local setup before executing reviews:
```bash
python .github/skills/design-maturity-reviewer/scripts/doctor.py --page-id 123456
```

Sample Output:
```text
=== Design Maturity Reviewer: Environment Diagnostics ===
[PASS] Git Installation: git version 2.55.0.windows.3
[PASS] Python Version: Python 3.11.2 satisfies minimum requirement (>= 3.9).
[PASS] Required Packages: All required Python packages installed.
[PASS] Skill Folder Structure: Canonical skill directory and SKILL.md exist.
[PASS] Knowledge Index (Page 123456): Valid index manifest found (6 chunks, version 12).
[WARN] GitHub CLI (gh): gh CLI not authenticated. (Level 2 git history will be used as fallback).
[WARN] Atlassian Configuration: ATLASSIAN_BASE_URL not set. (Offline --from-file mode available).
===========================================================
Doctor check: PASSED (all mandatory prerequisites met).
```

---

## 5. Operating Modes

### Mode A: Ticket Review (View 1)
Audits the code for a specific Jira ticket against the design:
```bash
# Offline using fixture ticket
python .github/skills/design-maturity-reviewer/scripts/render_report.py ...

# In Copilot Agent Chat / CLI:
"Review ticket PAY-123 against page 123456"
```
Output:
- Machine-readable record: `design-status/<pageId>/runs/<run-id>.json`
- Human report: `design-status/<pageId>/tickets/<JIRA-KEY>.md`

### Mode B: Design Baseline Coverage (View 2)
Audits the complete repository at `origin/main` against all design sections:
```bash
python .github/skills/design-maturity-reviewer/scripts/rollup.py --page-id 123456
```
Output:
- Design Requirements Ledger: `design-status/<pageId>/requirements.json`
- Master Design Coverage: `design-status/<pageId>/COVERAGE.md`

### Preview Mode (`--preview`)
Reviews the engineer's active working tree (staged changes, unstaged edits, untracked files):
```bash
# Copilot prompt:
"Preview my branch against PAY-123 and page 123456"
```
All results are marked with a `PREVIEW (PROVISIONAL)` banner and quarantined under provisional sections in rollup until merged to `origin/main`.

### PR Mode (`--pr <number>`)
Resolves a specific PR head commit using GitHub CLI / API:
```bash
python .github/skills/design-maturity-reviewer/scripts/find_pr_evidence.py --jira-key PAY-123 --pr 142
```

---

## 6. Status & Evidence Rules

| Status | Definition | Evidence Requirement |
|---|---|---|
| **Implemented** | Satisfies all applicable acceptance criteria. | File path, line number, ±3 line snippet, snippet hash, and commit/PR attribution. |
| **Partial** | Some behaviour evidenced, but specific criteria remain incomplete. | Explains the exact missing criteria and next steps. |
| **Pending** | Targeted search found no qualifying implementation in code. | States search terms and confirmed lack of matching symbols. |
| **Unverifiable** | Cannot be proven via code alone (infra, multi-AZ latency, manual step). | Details specific human/operational verification steps required. |
| **Not yet assessed** | Requirement exists on design checklist but has not yet been audited. | Never reported as "Not implemented". |

### Orthogonal Flags
- `ambiguous`: Design lacks testable thresholds or metrics.
- `stale`: Previously verified code snippet no longer matches the source ref.
- `provisional`: Evidence exists only on an unmerged feature branch or working tree.

---

## 7. Anti-Hallucination Gate (`validate_report.py`)

DMR enforces a strict anti-hallucination verification gate before writing any assessment:
- Verifies that cited file paths exist at the target git ref.
- Verifies line numbers are within file bounds.
- Verifies that cited snippets match the actual code byte-for-byte.
- Fails loudly if an item is marked `Implemented` without qualifying code evidence.

```bash
python .github/skills/design-maturity-reviewer/scripts/validate_report.py \
  --report-file path/to/run.json \
  --ref origin/main
```

---

## 8. Deterministic Rollup & Squash Merge Revalidation

Unlike typical AI tools that re-query an LLM to aggregate coverage, `rollup.py` is **100% deterministic**:
1. **Hash-Based Content Revalidation**: When PRs are squash-merged, commit SHAs change. DMR searches for the normalized snippet hash in `origin/main`. When found, it automatically promotes provisional evidence to verified baseline without rerunning the LLM.
2. **Relocation Tolerant**: If a refactor moves a function from line 10 to line 35, DMR detects the relocation and updates the line number.
3. **Disagreement Detection**: If different ticket runs conflict, DMR reports the discrepancy for human review.

---

## 9. Repository Structure

```text
.github/
  agents/
    design-maturity-review.agent.md           # Thin custom agent picker definition
  prompts/
    dmr.prompt.md                             # VS Code /dmr shortcut prompt
  workflows/
    dmr-rollup.yml                            # Scheduled/push CI rollup workflow
  skills/
    design-maturity-reviewer/
      SKILL.md                                # Agent skill instructions (<200 lines)
      config/
        dmr.config.example.yml                # Configuration template
        schema.json                           # Configuration validation schema
      scripts/
        doctor.py                             # Diagnostics & environment checker
        config_loader.py                      # Config parser & validator
        preflight_index_check.py              # Manifest freshness & behind-origin check
        git_context.py                        # Ref, PR, and working tree snapshot resolver
        fetch_jira_ticket.py                  # Atlassian Cloud / DC REST client & AC parser
        fetch_design.py                       # Confluence design fetcher (API & offline)
        query_design_context.py               # FAISS vector search engine
        extract_requirements.py               # Atomic decomposition & ticket scope mapper
        search_code_evidence.py               # Ref-aware git grep & snippet extraction
        find_pr_evidence.py                   # 3-level PR fallback (gh -> log -> branch diff)
        attribute_evidence.py                 # git blame & PR attribution
        assess_requirements.py                # Completeness evaluation engine
        ledger.py                             # Immutable run records & requirements manager
        rollup.py                             # Deterministic hash-based coverage rollup
        validate_report.py                    # Anti-hallucination validation gate
        render_report.py                      # Markdown report generator
      references/                             # Detailed technical guidelines
      templates/                              # Report Markdown templates
      examples/                               # Sample outputs & offline fixtures
      tests/                                  # 14 test modules (40 automated tests)
tools/
  knowledge-ingestion/                        # Standalone FAISS indexer & chunker
knowledge-index/<pageId>/                     # Committed FAISS index & manifest.json
design-status/<pageId>/                       # Generated runs, tickets, and COVERAGE.md
requirements.txt                              # Python package dependencies
README.md                                     # Project documentation
```

---

## 10. Copilot Integration (Agent & Prompts)

### In VS Code Copilot Agent Chat
1. Open GitHub Copilot Chat in Agent Mode.
2. Type `@Design Maturity Reviewer` or use the `/dmr` prompt shortcut:
   ```text
   /dmr Review ticket PAY-123 against page 123456
   ```
3. To test your uncommitted branch changes:
   ```text
   /dmr Preview my branch against PAY-123 and page 123456
   ```

### Availability Rules
- The skill operates from `.github/skills/design-maturity-reviewer/` on your branch. Merge this folder into your repository's `main` branch so all engineers have immediate access.
- Works across Windows, macOS, and Linux.

---

## 11. Running Tests

DMR includes an automated, offline test suite covering all Git scenarios, ref relocations, squash merges, Jira AC parsing, vector queries, and anti-hallucination rules:

```bash
# Run complete test suite (40 tests across 14 modules)
python -m unittest discover -s .github/skills/design-maturity-reviewer/tests -p "test_*.py" -v
```

All tests execute completely offline without live external network dependencies using controlled temporary Git repositories and local vector indexes.

---

## 12. CI/CD Automation (GitHub Actions)

A ready-to-use GitHub Actions workflow is provided in `.github/workflows/dmr-rollup.yml`:
- **Triggers**: On push to `main` when run files change, on schedule (`cron`), or via `workflow_dispatch`.
- **Permissions**: Least-privilege `contents: write` to update `COVERAGE.md`.
- **Zero LLM Cost**: Rollup runs 100% deterministically using Python hashing.

---

## 13. Reusability & Multi-Team Adoption

To adopt DMR in another team or microservice:
1. Copy `.github/skills/design-maturity-reviewer/` and `tools/knowledge-ingestion/` into the new repository.
2. Ingest your team's Confluence design page:
   ```bash
   python tools/knowledge-ingestion/ingest.py --page-id <PAGE_ID> --output knowledge-index/<PAGE_ID>
   ```
3. Commit `knowledge-index/<PAGE_ID>/` to your repo.
4. Developers can immediately run reviews against their Jira tickets and branches!
