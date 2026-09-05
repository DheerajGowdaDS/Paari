"""Seed script — creates demo merchant, policies, agents, keypair, and governance data.

Seeded for MER-001 (Paari Demo Store). The legacy `merchant-demo-001` row
is also written as a backwards-compat alias so the existing test suite
(which references `merchant-demo-001` in `paari.db` and the runtime
loop's fallback) keeps working.
"""

from __future__ import annotations

import asyncio
import json
import os
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import text

from paari.config import settings
from paari.db.engine import get_session_maker, init_db

_KEYS_DIR = Path(__file__).resolve().parent / "authn" / "keys"


def _generate_keypair() -> None:
    """Generate an RSA keypair for RS256 JWT signing (gitignored)."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    _KEYS_DIR.mkdir(parents=True, exist_ok=True)
    private_path = _KEYS_DIR / "paari_private.pem"
    public_path = _KEYS_DIR / "paari_public.pem"

    if private_path.exists() and public_path.exists():
        return

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    private_path.write_bytes(private_pem)
    public_path.write_bytes(public_pem)
    os.chmod(private_path, 0o600)


async def _seed_policies(session) -> None:
    """Insert the PAARI / MERCHANT / STORE policy documents for MER-001."""
    from paari.memory.long_term import _load_json
    from paari.schemas.policy import PolicyLayer

    docs = [
        ("paari_policy.json", PolicyLayer.PAARI),
        ("merchant_demo.json", PolicyLayer.MERCHANT),
        ("store_demo.json", PolicyLayer.STORE),
    ]
    for filename, layer in docs:
        doc = _load_json(filename)
        await session.execute(
            text(
                "INSERT INTO policies (id, merchant_id, layer, version, document_json, is_active) "
                "VALUES (:id, :merchant_id, :layer, :version, :document_json, 1)"
            ),
            {
                "id": doc["policy_id"],
                "merchant_id": "MER-001",
                "layer": layer.value,
                "version": doc["version"],
                "document_json": json.dumps(doc),
            },
        )
    await session.commit()


async def _seed_merchants(session) -> None:
    """Insert MER-001 (canonical) and merchant-demo-001 (legacy alias)."""
    from paari.merchant_registry.merchant import MerchantStatus

    await session.execute(
        text(
            "INSERT INTO merchants "
            "(id, name, policy_version, shopify_domain, shopify_api_version, status, "
            " shopify_access_token_env, shopify_client_secret_env, avg_transaction_paise, active_hours_utc, "
            " agent_transactions_enabled, autonomous_limit_paise, display_id) "
            "VALUES (:id, :name, :version, :domain, :api_version, :status, :token_var, :secret_var, :avg, :active, :ate, :auto_lim, :display_id)"
        ),
        {
            "id": "MER-001",
            "name": "Paari Demo Store",
            "version": "v1",
            "domain": settings.shopify_domain,
            "api_version": settings.shopify_api_version,
            "status": MerchantStatus.AI_TRANSACTABLE.value,
            "token_var": settings.shopify_admin_token_var,
            "secret_var": settings.shopify_client_secret_var,
            "avg": 120000,
            # AI-transactable storefront (blueprint Phase 15): available 24/7 to
            # AI agents, not a human shop with closing time. 0..23 keeps the
            # canonical demo transaction inside active hours regardless of when
            # the demo runs; the unusual_hour risk rule still fires for real
            # merchants that declare narrower hours.
            "active": json.dumps(list(range(0, 24))),
            "ate": 1,
            "auto_lim": 2000000,
            "display_id": "MER-001",
        },
    )
    # Legacy alias so the existing test suite and runtime fallback keep working.
    await session.execute(
        text(
            "INSERT OR IGNORE INTO merchants "
            "(id, name, policy_version, shopify_domain, shopify_api_version, status, active_hours_utc) "
            "VALUES (:id, :name, :version, :domain, :api_version, :status, :active)"
        ),
        {
            "id": "merchant-demo-001",
            "name": settings.demo_merchant_name,
            "version": "v1",
            "domain": settings.shopify_domain,
            "api_version": settings.shopify_api_version,
            "status": MerchantStatus.AI_TRANSACTABLE.value,
            "active": json.dumps(list(range(0, 24))),
        },
    )
    await session.commit()


async def _seed_agents(session) -> None:
    from paari.schemas.capability import Capability

    buyer_caps = [
        "catalog.read",
        "inventory.read",
        "product.read",
        "quote.request",
        "quote.accept",
        "payment.request",
        "payment.mandate_charge",
        "payment.execute",
        "order.read",
    ]
    merchant_caps = [
        "catalog.search",
        "catalog.read",
        "inventory.read",
        "product.read",
        "quote.create",
        "quote.respond",
        "deal.negotiate",
        "order.read",
        "order.create",
    ]

    # Add a2a_endpoint column if it doesn't exist (Phase 2 migration)
    try:
        await session.execute(text("ALTER TABLE agents ADD COLUMN a2a_endpoint TEXT"))
    except Exception:
        pass  # Column may already exist

    # New canonical agents with governance identity columns
    await session.execute(
        text(
            "INSERT OR REPLACE INTO agents (id, merchant_id, agent_type, capabilities_json, display_id, owner_id, a2a_endpoint) "
            "VALUES (:id, NULL, :type, :caps, :display_id, :owner_id, :a2a_endpoint)"
        ),
        {
            "id": "BA-001",
            "type": "BUYER",
            "caps": json.dumps(buyer_caps),
            "display_id": "BA-001",
            "owner_id": "USER-001",
            "a2a_endpoint": "http://localhost:8000/a2a/buyer",  # Buyer agent endpoint (Paari gateway)
        },
    )
    await session.execute(
        text(
            "INSERT OR REPLACE INTO agents (id, merchant_id, agent_type, capabilities_json, display_id, owner_id, a2a_endpoint) "
            "VALUES (:id, :merchant_id, :type, :caps, :display_id, :owner_id, :a2a_endpoint)"
        ),
        {
            "id": "MA-001",
            "merchant_id": "MER-001",
            "type": "MERCHANT",
            "caps": json.dumps(merchant_caps),
            "display_id": "MA-001",
            "owner_id": "MER-001",
            "a2a_endpoint": "http://localhost:8000/a2a/merchant",  # Merchant agent endpoint (Paari gateway)
        },
    )
    # Legacy aliases so the existing tests' tokens still work.
    await session.execute(
        text(
            "INSERT OR IGNORE INTO agents (id, merchant_id, agent_type, capabilities_json) VALUES (:id, NULL, :type, :caps)"
        ),
        {"id": "buyer-agent-001", "type": "BUYER", "caps": json.dumps(buyer_caps)},
    )
    await session.execute(
        text(
            "INSERT OR IGNORE INTO agents (id, merchant_id, agent_type, capabilities_json) "
            "VALUES (:id, :merchant_id, :type, :caps)"
        ),
        {
            "id": "merchant-agent-001",
            "merchant_id": "merchant-demo-001",
            "type": "MERCHANT",
            "caps": json.dumps(merchant_caps),
        },
    )
    await session.commit()


async def _seed_governance(session) -> None:
    """Insert governance seed rows: user, user_policy, quote, transaction, payment_session, capability."""
    now = datetime.now(UTC)
    expires_at = now + timedelta(hours=1)
    session_expires = now + timedelta(minutes=10)

    # USER-001
    await session.execute(
        text(
            "INSERT INTO users (id, display_id, name, status) "
            "VALUES (:id, :display_id, :name, :status)"
        ),
        {
            "id": "USER-001",
            "display_id": "USER-001",
            "name": "Demo Buyer",
            "status": "ACTIVE",
        },
    )

    # User policy for USER-001
    await session.execute(
        text(
            "INSERT INTO user_policies (id, user_id, max_transaction_amount, daily_spending_limit, "
            " autonomous_payment, confirmation_threshold) "
            "VALUES (:id, :user_id, :max_tx, :daily, :auto, :threshold)"
        ),
        {
            "id": "UP-001",
            "user_id": "USER-001",
            "max_tx": 500_000,  # ₹5,000 — allows ₹4,799
            "daily": 1_000_000,  # ₹10,000
            "auto": 1,  # autonomous payment enabled
            "threshold": 500_000,  # ₹5,000 — ₹4,799 is below threshold, passes
        },
    )

    # QUOTE-001 (ACCEPTED, amount 479900 paise = ₹4,799, expires in 1h, linked to TXN-001)
    await session.execute(
        text(
            "INSERT INTO quotes (id, transaction_id, merchant_id, amount_paise, expires_at, state) "
            "VALUES (:id, :tx_id, :merchant_id, :amount, :expires_at, :state)"
        ),
        {
            "id": "QUOTE-001",
            "tx_id": "TXN-001",
            "merchant_id": "MER-001",
            "amount": 479_900,
            "expires_at": expires_at.isoformat(),
            "state": "ACCEPTED",
        },
    )

    # TXN-001 (GOVERNANCE_PENDING)
    await session.execute(
        text(
            "INSERT INTO transactions (id, merchant_id, buyer_agent_id, quote_id, amount_paise, currency, "
            " state, policy_version, display_id, merchant_agent_id) "
            "VALUES (:id, :merchant_id, :buyer, :quote_id, :amount, :currency, :state, :pv, :display_id, :ma_id)"
        ),
        {
            "id": "TXN-001",
            "merchant_id": "MER-001",
            "buyer": "BA-001",
            "quote_id": "QUOTE-001",
            "amount": 479_900,
            "currency": "INR",
            "state": "GOVERNANCE_PENDING",
            "pv": "v1",
            "display_id": "TXN-001",
            "ma_id": "MA-001",
        },
    )

    # PS-001 (payment session, ACTIVE, expires in 10 min)
    await session.execute(
        text(
            "INSERT INTO payment_sessions (id, display_id, transaction_id, authorized_amount, currency, status, expires_at) "
            "VALUES (:id, :display_id, :tx_id, :amount, :currency, :status, :expires_at)"
        ),
        {
            "id": "PS-001",
            "display_id": "PS-001",
            "tx_id": "TXN-001",
            "amount": 479_900,
            "currency": "INR",
            "status": "ACTIVE",
            "expires_at": session_expires.isoformat(),
        },
    )

    # CAP-001 (payment.execute, ONE_TIME, unused)
    await session.execute(
        text(
            "INSERT INTO payment_capabilities (id, display_id, transaction_id, action, max_amount, usage, used) "
            "VALUES (:id, :display_id, :tx_id, :action, :max_amount, :usage, :used)"
        ),
        {
            "id": "CAP-001",
            "display_id": "CAP-001",
            "tx_id": "TXN-001",
            "action": "payment.execute",
            "max_amount": 479_900,
            "usage": "ONE_TIME",
            "used": 0,
        },
    )

    # MAND-001 (demo mandate for USER-001: 5,000/tx, 10,000/day, MER-001 only)
    await session.execute(
        text(
            "INSERT INTO mandates (id, display_id, user_id, provider, instrument_reference, status, "
            " max_per_transaction, daily_limit, allowed_merchants_json, allowed_categories_json, "
            " autonomous_enabled, requires_review_above) "
            "VALUES (:id, :display_id, :user_id, :provider, :ref, :status, "
            " :max_tx, :daily, :merchants, :categories, :auto, :review_above)"
        ),
        {
            "id": "MAND-001",
            "display_id": "MAND-001",
            "user_id": "USER-001",
            "provider": "RAZORPAY",
            "ref": "rzp_mandate_demo_001",
            "status": "ACTIVE",
            "max_tx": 500_000,
            "daily": 1_000_000,
            "merchants": json.dumps(["MER-001"]),
            "categories": json.dumps([]),
            "auto": 1,
            "review_above": 300_000,
        },
    )

    await session.commit()


async def _seed_dashboard_user(session) -> None:
    await session.execute(
        text(
            "INSERT INTO dashboard_users (id, email, password, merchant_id) "
            "VALUES (:id, :email, :password, :merchant_id)"
        ),
        {
            "id": "dashboard-user-001",
            "email": settings.dashboard_user,
            "password": settings.dashboard_password,
            "merchant_id": "MER-001",
        },
    )
    # Legacy alias binding so the existing dashboard login still works.
    await session.execute(
        text(
            "UPDATE dashboard_users SET merchant_id = :alias WHERE id = :id AND merchant_id = :mid"
        ),
        {"alias": "merchant-demo-001", "id": "dashboard-user-001", "mid": "MER-001"},
    )
    await session.commit()


async def seed_async() -> None:
    """Async version of seed for calling from other async contexts."""
    await init_db()
    session_maker = get_session_maker()

    async with session_maker() as session:
        await session.execute(text("DELETE FROM payment_capabilities WHERE id IN ('CAP-001')"))
        await session.execute(text("DELETE FROM payment_sessions WHERE id IN ('PS-001')"))
        await session.execute(text("DELETE FROM quotes WHERE id IN ('QUOTE-001')"))
        await session.execute(text("DELETE FROM transactions WHERE id IN ('TXN-001')"))
        await session.execute(text("DELETE FROM user_policies WHERE id IN ('UP-001')"))
        await session.execute(
            text("DELETE FROM mandate_daily_usage WHERE mandate_id IN ('MAND-001')")
        )
        await session.execute(text("DELETE FROM mandates WHERE id IN ('MAND-001')"))
        await session.execute(text("DELETE FROM users WHERE id IN ('USER-001')"))
        await session.execute(
            text("DELETE FROM dashboard_users WHERE email = :email"),
            {"email": settings.dashboard_user},
        )
        await session.execute(
            text(
                "DELETE FROM agents WHERE id IN ('BA-001', 'MA-001', 'buyer-agent-001', 'merchant-agent-001')"
            )
        )
        await session.execute(
            text("DELETE FROM merchants WHERE id IN ('MER-001', 'merchant-demo-001')")
        )
        await session.execute(
            text("DELETE FROM policies WHERE merchant_id IN ('MER-001', 'merchant-demo-001')")
        )
        await session.commit()

        await _seed_merchants(session)
        await _seed_agents(session)
        await _seed_policies(session)
        # Mirror the freshly-inserted MER-001 policy rows onto the legacy alias
        # (distinct ids avoid PK collisions) so `for_merchant(merchant-demo-001)`
        # resolves them — the backwards-compat row's docstring promise.
        await session.execute(
            text(
                "INSERT OR IGNORE INTO policies "
                "(id, merchant_id, layer, version, document_json, is_active) "
                "SELECT id || '-ALIAS', 'merchant-demo-001', layer, version, document_json, is_active "
                "FROM policies WHERE merchant_id = 'MER-001'"
            )
        )
        await session.commit()
        await _seed_governance(session)
        await _seed_dashboard_user(session)

    _generate_keypair()
    print(
        "seed complete: MER-001 (+ legacy alias merchant-demo-001) BA-001 MA-001 USER-001 TXN-001"
    )


async def main_async() -> None:
    """Initialize the database and seed all demo data."""
    await seed_async()


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
