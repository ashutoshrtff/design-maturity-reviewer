# Status Definitions & Rules

## Implementation Statuses

### 1. Implemented
- The available code evidence satisfies all applicable acceptance criteria for the requirement.
- **Evidence Requirement**: File path, valid line number, bounded snippet (±3 lines), normalized SHA-256 hash, and delivering commit/PR attribution.
- **Rule**: Never mark Implemented without code evidence. Passing unit tests or a Jira ticket in "Done" state alone does not qualify.

### 2. Partial
- Some required behaviour is evidenced in code, but one or more acceptance criteria remain incomplete or missing.
- **Reporting Requirement**: Must state precisely what criteria are missing or incomplete and suggest next actions.

### 3. Pending
- A targeted search across configured search paths found no qualifying implementation evidence in code at the specified Git ref.
- **Rule**: Do not report Pending merely because no reviewed ticket claims the requirement. Status reflects code reality, not ticket claims.

### 4. Unverifiable
- The requirement cannot be conclusively verified through static source code inspection alone (e.g., cross-AZ failover SLA under 500ms, multi-region database latency, manual operational procedures).
- **Reporting Requirement**: Must detail human verification steps (e.g., AWS CloudWatch alarms, Chaos engineering drill reports).

### 5. Not yet assessed
- The requirement exists in the design checklist but has not yet been audited.
- **Rule**: Never report "Not yet assessed" as "Not implemented".

---

## Status Flags (Orthogonal to Status)

- `ambiguous`: The design specification or acceptance criteria are too vague, subjective, or lacking in measurable thresholds to judge objectively.
- `stale`: Previously verified code evidence no longer matches the current source code at the target ref.
- `provisional`: Code evidence exists on a feature branch or uncommitted working tree and has not yet been verified on `origin/main`.
