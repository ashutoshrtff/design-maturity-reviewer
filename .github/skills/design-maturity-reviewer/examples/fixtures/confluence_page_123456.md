# Instant Payment Settlement Engine
Architecture and operational requirements for real-time payment settlement.

## 1. Idempotency & Duplicate Request Protection
All incoming payment settlement requests to `/v1/settlements` must provide a unique `Idempotency-Key` HTTP header.
The engine must check if the key was previously processed:
- If key was processed within 24 hours, return HTTP 200 with the cached response and `X-Cache: HIT`.
- If key is currently being processed, return HTTP 409 Conflict with code `IDEMPOTENCY_CONCURRENT_REQUEST`.

## 2. Dynamic Transaction Fee Calculation
The settlement processor must calculate transaction fees according to tier rules:
- Tier 1 (< $1,000): 0.5% + $0.10 flat fee.
- Tier 2 ($1,000 - $10,000): 0.35% + $0.25 flat fee.
- Tier 3 (> $10,000): 0.20% flat fee.
Fee calculation must be logged with field `calculated_fee_cents`.

## 3. High Availability Multi-AZ Failover
Database failover must switch to secondary replica across AWS Availability Zones in under 500ms without data loss.

## 4. End-of-Day Audit Log Archival
Settlement audit records older than 30 days must be automatically compressed and uploaded to AWS S3 bucket `settlement-audit-archive`.

## 5. Performance and Latency
System performance must feel suitably snappy and scalable under peak holiday loads.
