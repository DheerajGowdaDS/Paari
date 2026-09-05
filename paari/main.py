"""FastAPI application entrypoint."""

from __future__ import annotations

from fastapi import FastAPI

from paari.api import agent, audit, auth, gateway, reviews, tools
from paari.api.a2a_agents import router as a2a_agents_router
from paari.api.a2a_gateway import router as a2a_gateway_router
from paari.api.api_auth import router as api_auth_router
from paari.api.api_autorun import router as api_autorun_router
from paari.api.api_buyer import router as api_buyer_router
from paari.api.api_merchant import router as api_merchant_router
from paari.api.checkout import router as checkout_router
from paari.api.discovery import router as discovery_router
from paari.api.health import router as health_router
from paari.api.jwks import router as jwks_router
from paari.api.mandates import router as mandates_router
from paari.api.payments import router as payments_router
from paari.api.razorpay_webhook import router as razorpay_webhook_router
from paari.api.webhooks import router as webhooks_router
from paari.dashboard.routes import router as dashboard_router
from paari.db.engine import init_db

app = FastAPI(title="Paari", version="0.1.0")

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3001", "http://127.0.0.1:3001"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(agent.router)
app.include_router(a2a_agents_router)
app.include_router(a2a_gateway_router)
app.include_router(tools.router)
app.include_router(reviews.router)
app.include_router(audit.router)
app.include_router(auth.router)
app.include_router(api_auth_router)
app.include_router(api_autorun_router)
app.include_router(api_buyer_router)
app.include_router(api_merchant_router)
app.include_router(gateway.router)
app.include_router(jwks_router)
app.include_router(dashboard_router)
app.include_router(webhooks_router)
app.include_router(razorpay_webhook_router)
app.include_router(mandates_router)
app.include_router(payments_router)
app.include_router(checkout_router)
app.include_router(discovery_router)
app.include_router(health_router)


@app.on_event("startup")
async def _startup() -> None:
    from paari.config import settings

    if settings.init_db:
        await init_db()

    # Start webhook worker and register subscriptions if base URL is configured
    if settings.webhook_base_url:
        from paari.webhooks.worker import start_worker

        start_worker()

        # Register webhook subscriptions with Shopify
        try:
            from paari.shopify_admin.webhooks import register_webhooks

            await register_webhooks("MER-001", settings.webhook_base_url)
        except Exception as e:
            import logging

            logging.getLogger("paari").warning("Webhook registration failed: %s", e)

    # Start store context refresh timer in live mode
    if settings.shopify_mode == "live":
        from paari.store_context.builder import get_store_context

        builder = get_store_context()
        builder.start_refresh_timer("MER-001", settings.store_context_ttl_seconds)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "paari"}
