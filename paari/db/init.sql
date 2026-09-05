-- Paari database schema (Postgres-compatible; runs on SQLite for the demo).
-- All timestamps are UTC. All IDs are UUIDs stored as CHAR(36).
-- Every table carries merchant_id for tenant isolation.

CREATE TABLE IF NOT EXISTS merchants (
    id            CHAR(36)      NOT NULL,
    name          VARCHAR(255)  NOT NULL,
    policy_version VARCHAR(32)   NOT NULL DEFAULT 'v1',
    shopify_domain VARCHAR(255),
    shopify_api_version VARCHAR(16) NOT NULL DEFAULT '2025-01',
    status        VARCHAR(16)   NOT NULL DEFAULT 'AI_TRANSACTABLE',
    shopify_access_token_env VARCHAR(64) NOT NULL DEFAULT 'SHOPIFY_ADMIN_ACCESS_TOKEN',
    shopify_client_secret_env VARCHAR(64) NOT NULL DEFAULT 'SHOPIFY_CLIENT_SECRET',
    avg_transaction_paise BIGINT NOT NULL DEFAULT 0,
    active_hours_utc TEXT NOT NULL DEFAULT '[]',
    agent_transactions_enabled INTEGER NOT NULL DEFAULT 1,
    autonomous_limit_paise BIGINT NOT NULL DEFAULT 2000000,
    display_id      VARCHAR(32)   UNIQUE,
    created_at    TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
);
CREATE INDEX IF NOT EXISTS idx_merchants_domain ON merchants(shopify_domain);

CREATE TABLE IF NOT EXISTS agents (
    id              CHAR(36)      NOT NULL,
    merchant_id     CHAR(36),
    agent_type      VARCHAR(16)   NOT NULL,          -- BUYER | MERCHANT | SYSTEM
    capabilities_json TEXT        NOT NULL DEFAULT '[]',
    display_id      VARCHAR(32)   UNIQUE,
    owner_id        CHAR(36),
    status          VARCHAR(16)   NOT NULL DEFAULT 'ACTIVE',
    revoked_at      TIMESTAMP,
    created_at      TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    FOREIGN KEY (merchant_id) REFERENCES merchants(id)
);

CREATE TABLE IF NOT EXISTS policies (
    id           CHAR(36)      NOT NULL,
    merchant_id  CHAR(36)      NOT NULL,
    layer        VARCHAR(16)   NOT NULL,           -- PAARI | MERCHANT | STORE | TX
    version      VARCHAR(32)   NOT NULL,
    document_json TEXT         NOT NULL,
    is_active    INTEGER       NOT NULL DEFAULT 1,
    created_at   TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    FOREIGN KEY (merchant_id) REFERENCES merchants(id)
);

CREATE TABLE IF NOT EXISTS transactions (
    id                       CHAR(36)    NOT NULL,
    merchant_id              CHAR(36)    NOT NULL,
    buyer_agent_id           CHAR(36)    NOT NULL,
    quote_id                 CHAR(36),
    amount_paise             BIGINT      NOT NULL,
    currency                 CHAR(3)     NOT NULL DEFAULT 'INR',
    state                    VARCHAR(32) NOT NULL,        -- REQUESTED|AUTHORIZED|POLICY_APPROVED|QUOTE_CREATED|PAYMENT_PENDING|PAYMENT_VERIFIED|ORDER_CONFIRMED|COMPLETED|DENIED
    policy_version           VARCHAR(32) NOT NULL,
    display_id               VARCHAR(32) UNIQUE,
    merchant_agent_id         CHAR(36),
    razorpay_order_id        VARCHAR(128),
    razorpay_payment_id      VARCHAR(128),
    payment_session_id       CHAR(36),
    buyer_credential_json    TEXT,
    mandate_id               CHAR(36),
    created_at               TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at               TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    FOREIGN KEY (merchant_id) REFERENCES merchants(id)
);

CREATE TABLE IF NOT EXISTS quotes (
    id            CHAR(36)    NOT NULL,
    transaction_id CHAR(36)   NOT NULL,
    merchant_id   CHAR(36)    NOT NULL,
    product_sku   VARCHAR(128),
    quantity      INTEGER     NOT NULL DEFAULT 1,
    amount_paise  BIGINT      NOT NULL,
    expires_at    TIMESTAMP   NOT NULL,
    state         VARCHAR(32) NOT NULL,          -- DRAFT|PENDING|ACCEPTED|EXPIRED
    created_at    TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    FOREIGN KEY (transaction_id) REFERENCES transactions(id),
    FOREIGN KEY (merchant_id) REFERENCES merchants(id)
);

CREATE TABLE IF NOT EXISTS payments (
    id              CHAR(36)    NOT NULL,
    transaction_id  CHAR(36)    NOT NULL,
    gateway_ref     VARCHAR(128),
    state           VARCHAR(32) NOT NULL,          -- PENDING | VERIFIED | FAILED
    verified_at     TIMESTAMP,
    created_at      TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    FOREIGN KEY (transaction_id) REFERENCES transactions(id)
);

CREATE TABLE IF NOT EXISTS payment_events (
    id            CHAR(36)    NOT NULL,
    transaction_id CHAR(36)   NOT NULL,
    event_type    VARCHAR(64) NOT NULL,
    payload_json  TEXT,
    created_at    TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    FOREIGN KEY (transaction_id) REFERENCES transactions(id)
);

CREATE TABLE IF NOT EXISTS reviews (
    id             CHAR(36)    NOT NULL,
    merchant_id    CHAR(36)    NOT NULL,
    transaction_id CHAR(36)    NOT NULL,
    triggered_by   VARCHAR(16) NOT NULL,           -- POLICY | RISK
    reason         TEXT        NOT NULL,
    sla_expires_at TIMESTAMP   NOT NULL,
    decision       VARCHAR(16),                    -- null until decided
    decided_by     VARCHAR(64),
    note           TEXT,
    decided_at     TIMESTAMP,
    pending_step_json TEXT,
    gateway_context_json TEXT,
    created_at     TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    FOREIGN KEY (transaction_id) REFERENCES transactions(id)
);

CREATE TABLE IF NOT EXISTS audit_events (
    id           CHAR(36)    NOT NULL,
    request_id   CHAR(36)    NOT NULL,
    merchant_id  CHAR(36),
    agent_id     CHAR(36),
    action       VARCHAR(64) NOT NULL,
    decision     VARCHAR(16) NOT NULL,              -- ALLOW | DENY | REVIEW | EXECUTED | FAILED
    policy_version VARCHAR(32),
    risk_score   INTEGER,
    payload_json TEXT,
    created_at   TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS jwt_revocations (
    jti         CHAR(36)    NOT NULL,
    revoked_at  TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at  TIMESTAMP   NOT NULL,
    PRIMARY KEY (jti)
);

CREATE TABLE IF NOT EXISTS dashboard_users (
    id       CHAR(36)    NOT NULL,
    email    VARCHAR(255) NOT NULL UNIQUE,
    password VARCHAR(255) NOT NULL,
    merchant_id CHAR(36),
    is_active INTEGER     NOT NULL DEFAULT 1,
    PRIMARY KEY (id),
    FOREIGN KEY (merchant_id) REFERENCES merchants(id)
);

CREATE TABLE IF NOT EXISTS webhook_events (
    id            CHAR(36)     NOT NULL,
    source        VARCHAR(16)  NOT NULL,             -- SHOPIFY | RAZORPAY
    event_id      VARCHAR(128),
    merchant_id   CHAR(36),
    topic         VARCHAR(64)  NOT NULL,
    webhook_id    VARCHAR(128) NOT NULL,             -- X-Shopify-Webhook-Id
    payload_json  TEXT         NOT NULL,
    received_at   TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    processed_at  TIMESTAMP,
    status        VARCHAR(16)  NOT NULL DEFAULT 'PENDING',
    error         TEXT,
    PRIMARY KEY (id),
    UNIQUE (source, webhook_id),
    UNIQUE (source, event_id)
);
CREATE INDEX IF NOT EXISTS idx_webhook_events_status_received ON webhook_events (status, received_at);

CREATE TABLE IF NOT EXISTS store_contexts (
    merchant_id   CHAR(36)    NOT NULL,
    payload_json  TEXT        NOT NULL,             -- JSON body; Postgres jsonb when migrated
    fetched_at    TIMESTAMP   NOT NULL,
    source        VARCHAR(16) NOT NULL,             -- ADMIN | STOREFRONT_MCP
    PRIMARY KEY (merchant_id)
);

CREATE INDEX IF NOT EXISTS idx_audit_merchant_created ON audit_events (merchant_id, created_at);
CREATE INDEX IF NOT EXISTS idx_transactions_merchant_state ON transactions (merchant_id, state);
CREATE INDEX IF NOT EXISTS idx_reviews_sla ON reviews (merchant_id, sla_expires_at);
CREATE INDEX IF NOT EXISTS idx_audit_request ON audit_events (request_id);

-- Governance tables (Phase 1 additive schema)

CREATE TABLE IF NOT EXISTS users (
    id            CHAR(36)    NOT NULL,
    display_id    VARCHAR(32) UNIQUE,
    name          VARCHAR(255) NOT NULL,
    status        VARCHAR(16) NOT NULL DEFAULT 'ACTIVE',
    created_at    TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS user_policies (
    id                       CHAR(36)    NOT NULL,
    user_id                  CHAR(36)    NOT NULL,
    max_transaction_amount   BIGINT      NOT NULL,
    daily_spending_limit     BIGINT      NOT NULL,
    autonomous_payment       INTEGER     NOT NULL DEFAULT 1,
    confirmation_threshold   BIGINT      NOT NULL DEFAULT 0,
    created_at               TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS payment_sessions (
    id                CHAR(36)    NOT NULL,
    display_id        VARCHAR(32) UNIQUE,
    transaction_id    CHAR(36)    NOT NULL,
    authorized_amount BIGINT      NOT NULL,
    currency          CHAR(3)     NOT NULL DEFAULT 'INR',
    status            VARCHAR(16) NOT NULL DEFAULT 'ACTIVE',
    expires_at        TIMESTAMP   NOT NULL,
    created_at        TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    FOREIGN KEY (transaction_id) REFERENCES transactions(id)
);
CREATE INDEX IF NOT EXISTS idx_payment_sessions_tx ON payment_sessions(transaction_id);

CREATE TABLE IF NOT EXISTS payment_capabilities (
    id                CHAR(36)    NOT NULL,
    display_id        VARCHAR(32) UNIQUE,
    transaction_id    CHAR(36)    NOT NULL,
    action            VARCHAR(32) NOT NULL,
    max_amount        BIGINT      NOT NULL,
    usage             VARCHAR(16) NOT NULL DEFAULT 'ONE_TIME',
    used              INTEGER     NOT NULL DEFAULT 0,
    created_at        TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    FOREIGN KEY (transaction_id) REFERENCES transactions(id)
);
CREATE INDEX IF NOT EXISTS idx_payment_capabilities_tx ON payment_capabilities(transaction_id);

-- Phase 3: mandate-based autonomous charging (instrument references only, never raw PAN)

CREATE TABLE IF NOT EXISTS mandates (
    id                       CHAR(36)    NOT NULL,
    display_id               VARCHAR(32) UNIQUE,
    user_id                  CHAR(36)    NOT NULL,
    provider                 VARCHAR(32) NOT NULL DEFAULT 'RAZORPAY',
    instrument_reference     VARCHAR(128) NOT NULL,
    status                   VARCHAR(16) NOT NULL DEFAULT 'ACTIVE',
    max_per_transaction      BIGINT      NOT NULL,
    daily_limit              BIGINT      NOT NULL,
    allowed_merchants_json   TEXT        NOT NULL DEFAULT '[]',
    allowed_categories_json  TEXT        NOT NULL DEFAULT '[]',
    autonomous_enabled       INTEGER     NOT NULL DEFAULT 1,
    requires_review_above    BIGINT      NOT NULL DEFAULT 0,
    expires_at               TIMESTAMP,
    created_at               TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    FOREIGN KEY (user_id) REFERENCES users(id)
);
CREATE INDEX IF NOT EXISTS idx_mandates_user_status ON mandates(user_id, status);

CREATE TABLE IF NOT EXISTS mandate_daily_usage (
    mandate_id  CHAR(36)    NOT NULL,
    day         CHAR(10)    NOT NULL,
    used_paise  BIGINT      NOT NULL DEFAULT 0,
    PRIMARY KEY (mandate_id, day),
    FOREIGN KEY (mandate_id) REFERENCES mandates(id)
);

-- Phase 2: A2A agent-to-agent communication

CREATE TABLE IF NOT EXISTS idempotency_keys (
    key             TEXT        NOT NULL,
    agent_id        CHAR(36)    NOT NULL,
    action          VARCHAR(64) NOT NULL,
    response_json   TEXT        NOT NULL,
    created_at      TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (key)
);
CREATE INDEX IF NOT EXISTS idx_idempotency_agent ON idempotency_keys(agent_id, action);

-- Add a2a_endpoint to agents table (Phase 2)
-- SQLite doesn't support ADD COLUMN IF NOT EXISTS in all versions, so we use a separate migration
