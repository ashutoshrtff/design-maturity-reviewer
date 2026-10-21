from fastapi import FastAPI, HTTPException, Request

app = FastAPI()

@app.post("/v1/settlements")
def create_settlement(request: Request):
    # Validate required Idempotency-Key header
    idempotency_key = request.headers.get("Idempotency-Key")
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="Missing required Idempotency-Key")

    # Check cache for duplicate request
    cached_response = check_idempotency_cache(idempotency_key)
    if cached_response:
        return {"status": "success", "cached": True, "headers": {"X-Cache": "HIT"}}

    # Transaction fee calculation
    fee_cents = calculate_tier_fee(request.amount_cents)
    log_settlement_event("settlement_processed", calculated_fee_cents=fee_cents)

    return {"status": "settled", "calculated_fee_cents": fee_cents}
