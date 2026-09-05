# Paari

**Paari** is a policy-governed LLM/agent platform for agentic commerce. It is built as a *control plane first*: an LLM proposes intent, and deterministic governance layers (authentication, authorization, policy engine, risk engine, tool gateway, audit) decide whether that intent becomes action. Shopify and Razorpay are downstream *environment adapters* — never peers of governance.

```text
                         PAARI CORE
                            │
                   ┌────────┴─────────┐
                   │                  │
                  LLM           Agent Runtime
                   │                  │
                   └────────┬─────────┘
                            │
                    Policy Context
                            │
       ┌────────────────────┼────────────────────┐
       ▼                    ▼                    ▼
 Governance             Authorization           Risk
 Engine                  Engine                Engine
       │                    │                    │
       └────────────────────┼────────────────────┘
                            ▼
                      Tool Gateway
                            │
                      Tool Registry
                            │
              ┌─────────────┼─────────────┐
              ▼             ▼             ▼
           Shopify       Razorpay      Other tools
           Adapter        Adapter
              │             │
              ▼             ▼
           STORE          PAYMENT
```

## Quick start

```bash
pip install -e ".[dev]"
cp .env.example .env          # fill in PAARI_LLM_API_KEY
python -m paari.seed          # seeds demo merchant, policies, agent, fixtures
uvicorn paari.main:app --reload
```

Then run the demo flow:

```bash
python scripts/buyer_flow.py
```

## Key design principles

- **Paari governance is the floor; merchant policies customize the ceiling.** Neither can be bypassed by the LLM.
- **Separation of intent from enforcement.** The LLM proposes; the gateway decides.
- **Payment success is never trusted from the agent.** Only a verified gateway/webhook event transitions payment state.
- **Typed schemas are the non-bypass defense.** Every tool input is a Pydantic model with `extra="forbid"`.
- **Every enforcement decision is audited synchronously** before the response returns.

See `plan/feature-governance-gateway-1.md` for the full specification.

## Governance Gateway

The Governance Gateway is a standalone transaction-level evaluator. It loads
agent/merchant/quote/policy/session/capability data, runs 10 independent rule
checks, aggregates with strict priority (DENY > REVIEW > ALLOW), transitions
the transaction through a 14-state machine, writes per-check audit events, and
exposes 3 curl-only endpoints.

### Quick start

```bash
# Seed the demo DB (creates USER-001/BA-001/MA-001/MER-001/TXN-001/PS-001/CAP-001)
make clean && make seed

# Run the 3-scenario demo
python scripts/governance_demo.py
```

### Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/gateway/governance/evaluate` | Evaluate governance for a transaction |
| `POST` | `/gateway/transactions` | Create a new transaction row |
| `POST` | `/gateway/transactions/{display_id}/authorize-payment` | Create payment session + capability, transition to PAYMENT_PENDING |

Example:

```bash
# Evaluate TXN-001
curl -X POST http://127.0.0.1:8000/gateway/governance/evaluate \
  -H "Content-Type: application/json" \
  -d '{"transaction_id": "TXN-001"}'
```

### Architecture

```
REQUEST
   │
   ▼
GovernanceEngine
   │
   ├── 9 rule checks (AGENT_IDENTITY, AGENT_AUTHORIZATION, ...)
   ├── PolicyEngine (delegated, via to_policy_context)
   ├── RiskEngine   (wrapped: LOW→PASS, MEDIUM/HIGH→REVIEW — risk never hard-denies)
   │
   ▼
aggregate → DENY / REVIEW / ALLOW
   │
   ├── audit_events row per check
   ├── GOVERNANCE_DECISION audit row
   └── state machine transition (15 states)
```

The engine delegates policy evaluation to the existing `paari/policy_engine` and
wraps the existing `paari/risk` engine. No duplicated policy truth.

## Razorpay Phase A — standalone verification

Phase A proves Razorpay Test Mode works end-to-end **without wiring it into the
Paari gateway**.  Run these commands in order:

```bash
# 1. Install deps (adds razorpay SDK)
pip install -e ".[dev]"

# 2. Configure Razorpay credentials (in .env, gitignored)
#    RAZORPAY_KEY_ID=rzp_test_...
#    RAZORPAY_KEY_SECRET=...

# 3. Verify the live API chain (order create → fetch → signature check)
python scripts/razorpay_sanity.py --amount 10000

# 4. Open the browser checkout page
python scripts/razorpay_checkout_server.py --port 8901
# Then visit http://127.0.0.1:8901/checkout
```

### What Phase A covers

| Step | What happens |
|---|---|
| `razorpay_sanity.py` | Creates a real Test Mode order, fetches it, and proves the HMAC-SHA256 verifier is correct |
| `razorpay_checkout_server.py` | Browser page → `checkout.js` modal → pay with `success@razorpay` → signature verified server-side |
| `tests/test_razorpay_sanity.py` | Offline unit tests + gated live tests (skipped when `RAZORPAY_KEY_ID` is absent) |

**Security notes**

- `RAZORPAY_KEY_SECRET` lives only in `.env` (gitignored).  The checkout page receives only `key_id` (public).
- Signature verification uses `hmac.compare_digest` (timing-safe).
- Phase A does **not** create any Paari transaction records.  Webhooks, gateway wiring, and auto-fulfillment are deferred to Phase B (on explicit user instruction).

See `plan/feature-razorpay-phase-a-standalone-verification-1.md` for the full specification.

## Showcase — 4 Proof Cases + Dashboard Transaction View

Prove *"Every money action is explainable, bounded, gated, auditable"* with one reproducible script through the **real** Gateway/Payment/Governance stack.

```bash
python -m paari.seed
python scripts/showcase.py                # ASGI (no server needed) — runs A/B/C/D
python scripts/showcase.py --url http://127.0.0.1:8000   # live server
python -m pytest tests/test_showcase.py -v   # pytest version of same 4 cases
```

| Case | Setup | Proof |
|---|---|---|
| **A — ALLOW** | Quote Rs 4,799 below limit | ALLOW -> session ACTIVE + capability -> Razorpay `amount==authorized_amount` -> `payment.captured` webhook -> `PAYMENT_VERIFIED` -> audit timeline |
| **B — DENY** | Quote 4,799 but tx 7,999 (manipulation) | DENY `AMOUNT_MISMATCH` -> **0 sessions, 0 capabilities, adapter not called** |
| **C — REVIEW** | Autonomous disabled (Rs 7,000 > limit) | REVIEW -> dashboard `Approve` -> `ReviewService.decide()` re-executes gateway -> re-check -> ALLOW |
| **D — FAILED** | ALLOW then `simulate_failure` | `PAYMENT_FAILED` -> `payment.failed` event -> **no fulfillment / no ORDER_CONFIRMED** |

Dashboard: `GET /dashboard/transactions/{display_id}` shows **Decision -> Why (checks) -> Payment (session/capability/razorpay) -> Fulfillment -> Audit timeline** for each case (login via `/dashboard/login`).

> **Agents negotiate. Paari governs. Razorpay executes. Paari verifies. Merchant fulfills.**