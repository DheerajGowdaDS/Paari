#!/usr/bin/env python3
"""Razorpay Test Mode — standalone API sanity helpers.

No network calls on import.  All I/O lives inside the functions.

Usage:
    python scripts/razorpay_sanity.py --amount 10000
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import sys
from typing import Any

import razorpay

from paari.config import settings


# ── helpers ──────────────────────────────────────────────────────────

def require_razorpay_credentials() -> tuple[str, str]:
    """Return (key_id, key_secret) or exit with a clear message."""
    key_id = (settings.razorpay_key_id or "").strip()
    key_secret = (settings.razorpay_key_secret or "").strip()
    if not key_id or not key_secret:
        print(
            "ERROR: RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET are not set.\n"
            "Add them to your .env and re-run, e.g.:\n"
            "  RAZORPAY_KEY_ID=rzp_test_<YOUR_TEST_KEY_ID>\n"
            "  RAZORPAY_KEY_SECRET=<your secret>",
            file=sys.stderr,
        )
        sys.exit(1)
    return key_id, key_secret


def build_order_payload(
    amount_paise: int,
    receipt: str,
    notes: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build the dict passed to ``razorpay.Client.order.create``.

    Args:
        amount_paise: Amount in smallest currency unit (paise for INR).
        receipt:      Merchant-defined order identifier.
        notes:        Optional free-form key/value metadata (max 15 chars/value).

    Returns:
        Dict with keys ``amount``, ``currency``, ``receipt``, and ``notes``.
    """
    payload: dict[str, Any] = {
        "amount": amount_paise,
        "currency": "INR",
        "receipt": receipt,
        "notes": notes or {},
    }
    return payload


def verify_checkout_signature(
    order_id: str,
    payment_id: str,
    signature: str,
    key_secret: str,
) -> bool:
    """Verify the Razorpay checkout HMAC-SHA256 signature.

    Razorpay computes ``HMAC-SHA256( f"{order_id}|{payment_id}", key_secret )``
    and returns the hex-digest as the ``razorpay_signature`` field.

    Args:
        order_id:    The Razorpay order ID (``order_...`` or ``order_test_...``).
        payment_id:  The Razorpay payment ID from the checkout response.
        signature:   Hex-digest HMAC from the checkout response.
        key_secret:  Your Razorpay key secret (from ``.env``).

    Returns:
        ``True`` when the signature is valid, ``False`` otherwise.
    """
    message = f"{order_id}|{payment_id}".encode()
    expected = hmac.new(
        key_secret.encode(),
        message,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def create_test_order(
    key_id: str,
    key_secret: str,
    amount_paise: int,
    receipt: str,
) -> dict[str, Any]:
    """Create a Razorpay Test Mode order.

    Args:
        key_id:       Razorpay key ID (``rzp_test_...``).
        key_secret:   Matching key secret.
        amount_paise: Amount in paise (INR smallest unit).
        receipt:      Merchant-defined receipt string.

    Returns:
        Order dict from Razorpay (contains ``id``, ``status``, ``amount``, …).
    """
    client = razorpay.Client(auth=(key_id, key_secret))
    payload = build_order_payload(amount_paise, receipt)
    return client.order.create(payload)


def fetch_order(
    key_id: str,
    key_secret: str,
    order_id: str,
) -> dict[str, Any]:
    """Fetch a Razorpay order by ID.

    Args:
        key_id:     Razorpay key ID.
        key_secret: Matching key secret.
        order_id:   Razorpay order ID to retrieve.

    Returns:
        Order dict from Razorpay.
    """
    client = razorpay.Client(auth=(key_id, key_secret))
    return client.order.fetch(order_id)


# ── CLI ──────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Razorpay Test Mode sanity check (standalone, no Paari wiring).",
    )
    parser.add_argument(
        "--amount",
        type=int,
        default=10_000,
        nargs="?",
        help="Order amount in paise (default: 10000 = ₹100).",
    )
    parser.add_argument(
        "--receipt",
        default="paari_sanity_test",
        help="Receipt string for the order (default: paari_sanity_test).",
    )
    args = parser.parse_args()

    key_id, key_secret = require_razorpay_credentials()
    print(f"[cred] key_id={key_id[:10]}...  (secret redacted)")

    # ── Step 1: create order ────────────────────────────────────────
    print(f"\n[1/3] Creating order: amount={args.amount} paise  receipt={args.receipt!r}")
    try:
        order = create_test_order(key_id, key_secret, args.amount, args.receipt)
    except Exception as exc:
        print(f"  FAILED to create order: {exc}", file=sys.stderr)
        return 1

    order_id = order.get("id", "unknown")
    order_status = order.get("status", "unknown")
    print(f"  order_id  = {order_id}")
    print(f"  status    = {order_status}")
    print(f"  amount    = {order.get('amount')} {order.get('currency', 'INR')}")

    if order_status != "created":
        print(f"  WARNING: expected status 'created', got '{order_status}'", file=sys.stderr)

    # ── Step 2: fetch order ─────────────────────────────────────────
    print(f"\n[2/3] Fetching order {order_id}")
    try:
        fetched = fetch_order(key_id, key_secret, order_id)
    except Exception as exc:
        print(f"  FAILED to fetch order: {exc}", file=sys.stderr)
        return 1

    fetched_id = fetched.get("id", "unknown")
    fetched_status = fetched.get("status", "unknown")
    print(f"  fetched   id    = {fetched_id}")
    print(f"  fetched   status= {fetched_status}")

    if fetched_id != order_id:
        print(f"  FAILED: fetched id mismatch (expected {order_id}, got {fetched_id})", file=sys.stderr)
        return 1

    # ── Step 3: signature verifier self-check ───────────────────────
    print("\n[3/3] Signature verifier self-check")
    known_order_id = "order_test_selfcheck_001"
    known_payment_id = "pay_selfcheck_001"
    known_secret = "test_secret_key"

    expected_sig = hmac.new(
        known_secret.encode(),
        f"{known_order_id}|{known_payment_id}".encode(),
        hashlib.sha256,
    ).hexdigest()

    ok_good = verify_checkout_signature(known_order_id, known_payment_id, expected_sig, known_secret)
    ok_bad = verify_checkout_signature(known_order_id, known_payment_id, "deadbeef" * 8, known_secret)
    print(f"  known-good triple -> {ok_good}  (expected True)")
    print(f"  tampered sig      -> {ok_bad}  (expected False)")

    if not ok_good or ok_bad:
        print("  FAILED: verifier logic is broken", file=sys.stderr)
        return 1

    print("\n[OK] All checks passed.  Razorpay Test Mode is live and reachable.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
