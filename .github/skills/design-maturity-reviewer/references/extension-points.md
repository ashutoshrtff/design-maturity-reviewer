# DMR Extension Points (v1 Stubs & Roadmap)

The DMR core focuses strictly on design-to-implementation completeness. The following extension points are designed as decoupled hooks:

## 1. Automated PR Comments
- Post concise maturity summaries directly into PR discussion timelines via GitHub API when DMR runs in CI.

## 2. Test-Scenario Handoff
- Export `Partial` and `Pending` requirement acceptance criteria as structured JSON for ingestion by test-generation frameworks (e.g. pytest-bdd, Cucumber, Postman collections).

## 3. Multi-Repository Rollup
- Aggregate coverage across microservice architectures delivering against a single overarching enterprise design doc.

## 4. Organization Guardrails Pack
- Static policy checks validating design conformance (e.g. mandatory idempotency keys on payment endpoints, encryption at rest config flags).
