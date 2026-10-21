# Requirement Extraction & Classification

## Principles
1. **Atomic & Testable**: Each requirement represents a single distinct capability, validation rule, error handling path, or contract.
2. **Stable Identifiers**: Requirements receive persistent IDs (`R-001`, `R-002`, ...) stored in `requirements.json`. Unchanged requirements retain their ID even if extraction order changes.
3. **Traceability**: Every requirement tracks source citations: `page_id`, `heading_path`, and `chunk_id`.

## Classification Types
- `functional`: Core business logic, settlement calculations, workflow steps.
- `validation`: Header checks, payload schema validation, bounds checks.
- `error_handling`: HTTP 4xx/5xx status codes, error models, concurrency conflicts.
- `configuration`: Environment variables, feature flags, timeout parameters.
- `integration_contract`: REST endpoints, Kafka topics, S3 buckets, database schemas.
- `non_functional`: Latency, throughput, scalability, high availability.

## Scope Creep & Ticket Items with No Design Basis
When a Jira ticket introduces acceptance criteria or features not present on the Confluence design page (e.g. exporting to Excel spreadsheet), they are classified under **Ticket Items with No Design Basis** rather than as implementation gaps in the design.
