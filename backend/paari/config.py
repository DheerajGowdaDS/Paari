"""Application settings loaded from environment variables."""

from __future__ import annotations

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All configuration is env-driven. See .env.example for the full set."""

    model_config = SettingsConfigDict(
        env_prefix="PAARI_",
        env_file=".env",
        extra="ignore",
        populate_by_name=True,
    )

    # LLM API (OpenAI-compatible HTTPS endpoint — no GPU required)
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    llm_timeout_s: float = 30.0

    # Database
    db_url: str = "sqlite+aiosqlite:///paari.db"
    init_db: bool = True
    redis_url: str = "redis://localhost:6379/0"

    # Identity
    jwt_issuer: str = "paari-platform"
    jwt_expire_seconds: int = 900

    # Platform limits (smallest currency unit = paise for INR)
    max_autonomous_transaction_paise: int = 5_000_000
    payment_session_ttl_seconds: int = 600
    max_payment_retries: int = 3

    # Demo merchant seed
    demo_merchant_name: str = "Demo Shoes"
    demo_merchant_autonomous_limit_paise: int = 2_000_000

    # Dashboard
    dashboard_session_secret: str = "change-me"
    dashboard_user: str = "merchant@demo.local"
    dashboard_password: str = "demo"
    review_sla_hours: int = 4

    # Server
    host: str = "127.0.0.1"
    port: int = 8000

    # Commerce adapter (Shopify)
    shopify_mode: str = "stub"  # stub | live
    shopify_domain: str = "paari-demo-store.myshopify.com"
    shopify_api_version: str = "2025-01"
    shopify_admin_token_var: str = "SHOPIFY_ADMIN_ACCESS_TOKEN"
    shopify_client_secret_var: str = "SHOPIFY_CLIENT_SECRET"
    shopify_admin_access_token: str = ""  # set by user, never logged
    shopify_client_secret: str = ""  # set by user, never logged
    storefront_mcp_url: str = ""  # https://{domain}/api/mcp

    def resolved_storefront_mcp_url(self) -> str:
        """Return the Storefront MCP URL, deriving it from the domain if unset."""
        if self.storefront_mcp_url:
            return self.storefront_mcp_url
        return f"https://{self.shopify_domain}/api/mcp"

    # Store context caching
    store_context_ttl_seconds: int = 900  # 15 min
    store_policy_ttl_hours: int = 24

    # Layered buyer identity (Option 3 - blueprint Step 5/17)
    buyer_credential_required: bool = False
    buyer_credential_threshold_paise: int = 1_000_000
    buyer_credential_deny_if_missing: bool = False

    # Razorpay payment gateway
    razorpay_mode: str = "stub"  # stub | live
    razorpay_key_id: str = Field(
        default="", validation_alias=AliasChoices("RAZORPAY_KEY_ID", "PAARI_RAZORPAY_KEY_ID")
    )
    razorpay_key_secret: str = Field(
        default="",
        validation_alias=AliasChoices("RAZORPAY_KEY_SECRET", "PAARI_RAZORPAY_KEY_SECRET"),
    )
    razorpay_webhook_secret: str = Field(
        default="",
        validation_alias=AliasChoices("RAZORPAY_WEBHOOK_SECRET", "PAARI_RAZORPAY_WEBHOOK_SECRET"),
    )

    # Webhooks
    webhook_base_url: str = ""  # e.g. https://abc.ngrok-free.app
    webhook_topic_orders: str = "orders/create,orders/updated,orders/delete"
    webhook_topic_inventory: str = "inventory_levels/update"
    webhook_workers: int = 1


settings = Settings()
