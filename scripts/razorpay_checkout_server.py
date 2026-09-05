#!/usr/bin/env python3
"""Razorpay Checkout Server — Phase A standalone verification.

A minimal, self-contained FastAPI app that:
  - POST /checkout  creates a Razorpay order (via the Razorpay SDK)
  - GET  /checkout  serves the browser checkout page
  - POST /verify     verifies the checkout HMAC signature

Runs independently of the Paari gateway (REQ-001).

Usage:
    python scripts/razorpay_checkout_server.py --port 8901

Then open http://127.0.0.1:8901/checkout in a browser, enter an amount,
and pay with UPI ID ``success@razorpay`` (or ``failure@razorpay`` to test
the error path).
"""

from __future__ import annotations

import argparse
import sys
import uvicorn
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from paari.config import settings

from scripts.razorpay_sanity import (
    build_order_payload,
    create_test_order,
    fetch_order,
    require_razorpay_credentials,
    verify_checkout_signature,
)

# ── bootstrap ────────────────────────────────────────────────────────

key_id, key_secret = require_razorpay_credentials()

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

app = FastAPI(
    title="Paari Razorpay Checkout (Phase A)",
    description="Standalone Razorpay Test Mode verification server.",
    version="0.1.0",
)


# ── routes ───────────────────────────────────────────────────────────

@app.get("/checkout", response_class=HTMLResponse)
async def checkout_page(request: Request, amount: int = 100) -> HTMLResponse:
    """Serve the checkout page.

    Query param ``amount`` is in whole INR rupees (default 100).
    """
    amount_paise = max(1, amount) * 100
    return templates.TemplateResponse(
        "razorpay_checkout.html",
        {
            "request": request,
            "key_id": key_id,
            "amount_paise": amount_paise,
            "verify_url": "/verify",
        },
    )


@app.post("/checkout")
async def create_order(request: Request) -> JSONResponse:
    """Create a Razorpay order from an x-www-form-urlencoded ``amount`` field.

    The ``amount`` field is expected in paise (INR smallest unit).
    Returns ``{"order_id": ..., "receipt": ...}`` or ``{"error": ...}``.
    """
    raw = await request.body()
    try:
        body = dict(x.split("=", 1) for x in raw.decode().split("&") if "=" in x)
        amount_paise = int(body.get("amount", "10000"))
    except (ValueError, UnicodeDecodeError):
        return JSONResponse({"error": "Invalid request body"}, status_code=400)

    receipt = f"paari_phase_a_{amount_paise}"
    try:
        order = create_test_order(key_id, key_secret, amount_paise, receipt)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)

    return JSONResponse({
        "order_id": order.get("id", ""),
        "receipt": receipt,
        "amount": order.get("amount"),
        "currency": order.get("currency", "INR"),
    })


@app.post("/verify")
async def verify_payment(request: Request) -> JSONResponse:
    """Verify a Razorpay checkout signature.

    Expects JSON body:
        {"razorpay_order_id": "...", "razorpay_payment_id": "...", "razorpay_signature": "..."}

    On success also fetches the payment via the Razorpay API to confirm status.
    """
    body = await request.json()
    order_id   = body.get("razorpay_order_id", "")
    payment_id = body.get("razorpay_payment_id", "")
    signature  = body.get("razorpay_signature", "")

    if not all([order_id, payment_id, signature]):
        return JSONResponse({"verified": False, "error": "missing fields"}, status_code=400)

    ok = verify_checkout_signature(order_id, payment_id, signature, key_secret)

    result: dict = {
        "verified": ok,
        "order_id": order_id,
        "payment_id": payment_id,
    }

    if ok:
        try:
            order = fetch_order(key_id, key_secret, order_id)
            result["order_status"] = order.get("status")
            result["order_amount"] = order.get("amount")
        except Exception as exc:
            result["fetch_error"] = str(exc)

    status_code = 200 if ok else 400
    return JSONResponse(result, status_code=status_code)


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok", "key_id_prefix": key_id[:12]})


# ── main ─────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="Paari Razorpay Checkout Server (Phase A)")
    parser.add_argument("--port", type=int, default=8901, help="Port to listen on (default: 8901)")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address (default: 127.0.0.1)")
    args = parser.parse_args()

    print(f"Starting Razorpay Checkout Server on http://{args.host}:{args.port}")
    print(f"  GET  /checkout  - checkout page (browser)")
    print(f"  POST /checkout  - create Razorpay order")
    print(f"  POST /verify    - verify payment signature")
    print(f"  GET  /health    - health check")
    print(f"  key_id = {key_id[:16]}...  (secret redacted)")
    print()
    print(f"Open http://{args.host}:{args.port}/checkout in a browser to begin.")

    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
