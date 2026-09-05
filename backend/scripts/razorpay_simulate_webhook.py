#!/usr/bin/env python3
"""Simulate a Razorpay payment.authorized webhook for the demo.

Posts a signed webhook event to the Paari /razorpay/webhook endpoint (stub
implementation) so the payment transitions PENDING -> VERIFIED.

Usage:
    python scripts/razorpay_simulate_webhook.py --transaction-id <tx-id> --amount-paise 120000
"""

from __future__ import annotations

import argparse
import sys

import httpx

from paari.tools.adapters.razorpay_stub import build_verified_event


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument("--transaction-id", required=True)
    parser.add_argument("--amount-paise", type=int, required=True)
    args = parser.parse_args()

    event = build_verified_event(args.transaction_id, args.amount_paise)
    url = f"{args.base.rstrip('/')}/razorpay/webhook"
    r = httpx.post(url, json=event, timeout=10.0)
    print(f"posted to {url}: status={r.status_code} body={r.text[:200]}")
    return 0 if r.status_code == 200 else 1


if __name__ == "__main__":
    sys.exit(main())
