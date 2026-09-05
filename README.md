# Paari

**Paari** is a policy-governed agentic commerce platform: AI buyer and merchant agents negotiate a deal, and **Paari's deterministic governance layer decides whether that deal can become a payment**. The LLM proposes intent; authn, authz, policy, risk, the tool gateway and the audit trail decide whether intent becomes action. Shopify and Razorpay are downstream adapters — never peers of governance.

> **Every money action is explainable, bounded, gated, and auditable.**

## Repository layout (monorepo)

```
Paari/
├── backend/     FastAPI control plane (Python 3.11+)
│   ├── paari/               governance engine, payment service, A2A agents,
│   │                        adapters (Shopify/Razorpay), webhooks, audit, dashboard
│   ├── tests/               325 offline tests
│   ├── scripts/             demos, showcase, proof scripts
│   └── Makefile · pyproject.toml · .env.example · RUNBOOK.md
└── frontend/    Next.js dashboards (buyer / merchant / audit)
    ├── app/buyer/           governed autorun purchase flow
    ├── app/merchant/        merchant dashboard + review queue
    ├── app/audit/           audit timeline
    └── lib/                 typed backend API clients
```

## Quick start

**1. Backend** (see `backend/RUNBOOK.md` for full details):

```bash
cd backend
pip install -e ".[dev]"
cp .env.example .env      # add your keys (Shopify / Razorpay test / LLM)
make seed && make run     # http://127.0.0.1:8000
```

**2. Frontend**:

```bash
cd frontend
npm install
npm run dev               # http://localhost:3000
```

## Architecture

```text
                         PAARI CORE
                            │
                   ┌────────┴─────────┐
                  LLM           Agent Runtime
                   └────────┬─────────┘
                     Policy Context
       ┌────────────────────┼────────────────────┐
  Governance           Authorization           Risk
  Engine                Engine                Engine
       └────────────────────┼────────────────────┘
                      Tool Gateway
                      Tool Registry
              ┌─────────────┼─────────────┐
           Shopify       Razorpay      Other tools
           Adapter        Adapter
              │             │
           STORE          PAYMENT
```

The deal is agentic; the payment is governed:

```text
Buyer Agent ↔ Merchant Agent   →  final quote  →  PAARI GOVERNANCE
  → ALLOW / REVIEW / DENY
  → bounded payment session + one-time capability
  → Razorpay (human checkout, or mandate-based autonomous charge)
  → verified webhook  →  settlement  →  Shopify order  →  audit trail
```

## Proof

`backend/scripts/showcase.py` runs the four canonical cases — **ALLOW** (governed payment completes), **DENY** (amount manipulation blocked, Razorpay never called), **REVIEW** (human approval re-runs governance), **FAILED** (payment failure never fulfills) — and `backend/scripts/prove_phase1_path.py` proves the governance invariants including layered buyer identity.

```bash
cd backend
python scripts/showcase.py
```

Dashboard: `http://127.0.0.1:8000/dashboard/login` (or the Next.js frontend) shows every transaction's **Decision → Why → Payment → Fulfillment → Audit timeline**.

See `backend/README.md` (platform deep-dive), `backend/RUNBOOK.md` (operations), and `frontend/BACKEND_INTEGRATION.md` (API contract).
