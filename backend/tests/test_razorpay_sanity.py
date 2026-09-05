"""Razorpay Phase A sanity — offline unit tests + gated live tests.

Offline tests are always collected and run.
Live tests are skipped unless RAZORPAY_KEY_ID is present in the environment.
"""

from __future__ import annotations

import hashlib
import hmac
import os

import pytest

from scripts.razorpay_sanity import (
    build_order_payload,
    verify_checkout_signature,
)


# ── offline: verify_checkout_signature ─────────────────────────────

class TestVerifyCheckoutSignature:
    """Deterministic HMAC-SHA256 verifier tests — no network required."""

    @staticmethod
    def _sig(order_id: str, payment_id: str, secret: str) -> str:
        msg = f"{order_id}|{payment_id}".encode()
        return hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()

    def test_known_good_signature_returns_true(self):
        sig = self._sig("order_test_1", "pay_test_1", "secret123")
        assert verify_checkout_signature("order_test_1", "pay_test_1", sig, "secret123") is True

    def test_tampered_signature_returns_false(self):
        good_sig = self._sig("order_test_1", "pay_test_1", "secret123")
        tampered = "0" * len(good_sig)
        assert verify_checkout_signature("order_test_1", "pay_test_1", tampered, "secret123") is False

    def test_wrong_secret_returns_false(self):
        good_sig = self._sig("order_test_1", "pay_test_1", "secret123")
        assert verify_checkout_signature("order_test_1", "pay_test_1", good_sig, "other_secret") is False

    def test_empty_inputs_returns_false(self):
        assert verify_checkout_signature("", "", "", "") is False

    def test_uses_timing_safe_compare(self):
        import inspect
        src = inspect.getsource(verify_checkout_signature)
        assert "hmac.compare_digest" in src


# ── offline: build_order_payload ────────────────────────────────────

class TestBuildOrderPayload:

    def test_default_currency_is_inr(self):
        payload = build_order_payload(50_000, "rcpt-001")
        assert payload["currency"] == "INR"

    def test_amount_paise_passthrough(self):
        payload = build_order_payload(12345, "rcpt-002")
        assert payload["amount"] == 12345

    def test_receipt_stored(self):
        payload = build_order_payload(10_000, "my_receipt")
        assert payload["receipt"] == "my_receipt"

    def test_notes_default_empty_dict(self):
        payload = build_order_payload(10_000, "rcpt")
        assert payload["notes"] == {}

    def test_notes_passthrough(self):
        payload = build_order_payload(10_000, "rcpt", {"source": "web"})
        assert payload["notes"]["source"] == "web"

    def test_required_keys_present(self):
        payload = build_order_payload(1, "rcpt")
        assert set(payload.keys()) == {"amount", "currency", "receipt", "notes"}


# ── offline: credential gate ────────────────────────────────────────

class TestRequireRazorpayCredentials:

    def test_missing_credentials_exits(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr("scripts.razorpay_sanity.settings.razorpay_key_id", "")
        monkeypatch.setattr("scripts.razorpay_sanity.settings.razorpay_key_secret", "")
        with pytest.raises(SystemExit) as exc_info:
            from scripts.razorpay_sanity import require_razorpay_credentials
            require_razorpay_credentials()
        assert exc_info.value.code == 1

    def test_partial_credentials_exits(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr("scripts.razorpay_sanity.settings.razorpay_key_id", "rzp_test_xxx")
        monkeypatch.setattr("scripts.razorpay_sanity.settings.razorpay_key_secret", "")
        with pytest.raises(SystemExit):
            from scripts.razorpay_sanity import require_razorpay_credentials
            require_razorpay_credentials()


# ── live: gated behind env var ──────────────────────────────────────

HAS_CREDS = bool(os.getenv("RAZORPAY_KEY_ID") and os.getenv("RAZORPAY_KEY_SECRET"))


@pytest.mark.skipif(not HAS_CREDS, reason="RAZORPAY_KEY_ID/KEY_SECRET not set — skipping live tests")
class TestRazorpayLive:

    def test_create_and_fetch_order(self):
        from scripts.razorpay_sanity import create_test_order, fetch_order, require_razorpay_credentials
        key_id, key_secret = require_razorpay_credentials()
        order = create_test_order(key_id, key_secret, 10_000, "paari_live_test")
        assert "id" in order
        assert order["status"] == "created"
        fetched = fetch_order(key_id, key_secret, order["id"])
        assert fetched["id"] == order["id"]
