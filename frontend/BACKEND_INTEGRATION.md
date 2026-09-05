# Paari Web UI ↔ FastAPI Backend — Integration Brief

Answers to the 5 questions, endpoint contracts, and implementation order.
The web app is **built and running**; this document defines what the backend
must expose so the UI can be wired to it.

---

## 1. Pages & Flow

Next.js App Router, 4 routes. All UI copy/labels below are **already rendered**
by the frontend — the backend's job is to return data shaped like this, not to
change the UI.

| Route | Page | What it shows today (all mock/static) |
|---|---|---|
| `/` | Landing | Hero + two persona CTAs: **Buyer AI** → `/buyer`, **Merchant AI** → `/merchant` |
| `/buyer` | Buyer AI Console | Conversation thread: user ("Sovereign Principal") message → Buyer AI Agent reply with a **Proposed Settlement Package** ($42,500/mo, "Under Budget by $2,500", escrow digest `0x9d4b...83e1`, 50 nodes), buttons **Sign & Escrow $42,500/mo / Inspect Policy Limits / View Full Terms**, **Suggested Inquiries** chips, floating composer |
| `/merchant` | Merchant AI Console (Control Plane) | 3 columns: **Live Transaction Data Flow** (TXN-001, 10 steps), **Paari Architecture** flowchart, **Connections** (Shopify / Razorpay / A2A Protocol / LLM Service) + **System Health** (16/16 services, 4/4 webhooks, SQLite OK, 99.9% uptime, no alerts) |
| `/audit` | Full Audit Trail | TXN-001 ledger: summary tiles (Decision ALLOW · Checkpoints 10/10 · Duration 50s · Status SUCCESS), 10-step timeline, ledger footer ("LEDGER IMMUTABLE", digest) |

**Navigation:** header links on every page (Home / Buyer AI / Merchant / Audit).
IDs already present in the UI: `TXN-001` (transaction), `Q-001` (quote),
`BA-001` (buyer agent), `MA-001` (merchant agent), `sess_*` (session).

**Intended live flow:** Buyer principal types a procurement intent in the
composer → Buyer AI agent negotiates via A2A → returns a settlement package
(+ optional REVIEW/DENY) → principal signs & escrows → the transaction appears
in the Merchant console's Live Transaction Data Flow → payment verifies →
fulfillment → the same 10 steps show in Audit.

---

## 2. Stack

- **Framework:** Next.js **16.3.4**, App Router, React **19**, TypeScript strict.
- **Styling:** Tailwind CSS **v4** (custom design tokens in `app/globals.css`; no CSS framework classes in components beyond Tailwind utilities).
- **State:** React `useState` / `useRef` only — no Redux/Zustand. Add server-fetching via a small `fetch` wrapper (to be created when we wire).
- **Interactivity:** `/buyer` and `/merchant` are `"use client"` components.
- **Data today:** hardcoded in `lib/txnSteps.ts` (10-step timeline) and inline JSX (conversation, connections, health). These get replaced by API calls.
- **Icons:** Material Symbols (font) — the UI owns icon mapping; backend sends semantic `type`, not icon names.

---

## 3. Data Contracts

Base path: `/api` (see §5 — same-origin proxy, so the UI calls
`fetch("/api/...")`).

### Auth
| Endpoint | Purpose |
|---|---|
| `POST /api/auth/agent-token` | Exchange buyer/merchant credentials for a JWT |
| `GET /api/auth/me` | Resolve current session/identity (used on every page load) |

`POST /api/auth/agent-token`
```json
// request
{ "agent_type": "buyer" | "merchant", "agent_id": "BA-001", "credentials": { ... } }
// 200 response
{
  "access_token": "<jwt>",
  "token_type": "bearer",
  "expires_in": 3600,
  "agent": { "agent_id": "BA-001", "role": "buyer", "label": "Buyer AI" }
}
```
`GET /api/auth/me` → same `agent` object (or 401). Roles: `buyer`,
`merchant`, `operator`. Route guards: `/buyer` → buyer|operator;
`/merchant` → merchant|operator; `/audit` → operator.
The UI will support **either** JWT bearer (`Authorization: Bearer <token>`,
stored in localStorage) **or** an httpOnly `paari_session` cookie — pick one;
if cookie, the UI just needs `/api/auth/me` and cookies flow automatically
through the same-origin proxy.

### Buyer console
| Endpoint | Purpose |
|---|---|
| `POST /api/agent/buyer/chat` | Send principal intent → structured agent reply |
| `POST /api/escrow/authorize` | "Sign & Escrow" button |
| `GET /api/policies/limits` | "Inspect Policy Limits" |
| `GET /api/terms` | "View Full Terms" |

`POST /api/agent/buyer/chat`
```json
// request
{
  "session_id": "sess_01",
  "message": "Procure 50 enterprise seats for cloud GPU clusters (H100/H200) across verified merchants. Max spend $45,000/mo, SOC2 compliance required, dynamic settlement via escrow.",
  "context": { "agent_id": "BA-001", "budget_cap_monthly_usd": 45000 }
}
// 200 response — mirrors the existing settlement pane exactly
{
  "session_id": "sess_01",
  "reply": {
    "summary": "3 verified merchants matched; recommended: 50 H100 nodes at $42,500/mo.",
    "settlement": {
      "quote_id": "Q-001",
      "currency": "USD",
      "amount_monthly": 42500,
      "period_label": "/ month total commit (50 nodes aggregate)",
      "nodes": 50,
      "budget_cap_monthly": 45000,
      "under_budget": 2500,
      "status_label": "Under Budget by $2,500",
      "digest": "0x9d4b...83e1"
    },
    "actions": ["sign_escrow", "inspect_policy_limits", "view_full_terms"],
    "suggestions": [
      { "label": "Review SLA terms", "prompt": "Review SLA terms and downtime liability formulas" },
      { "label": "Simulate merchant failover", "prompt": "Simulate merchant failover scenarios under 100Gbps network loss" },
      { "label": "Adjust monthly budget ceiling", "prompt": "Adjust monthly budget ceiling to $60,000 and recalculate" }
    ],
    "decision": "ALLOW"          // ALLOW | REVIEW | DENY — see §Error handling
  }
}
```

`POST /api/escrow/authorize`
```json
// request
{ "quote_id": "Q-001", "amount_monthly": 42500, "digest": "0x9d4b...83e1" }
// 200 response (drives the existing "Escrow authorization queued" notification)
{
  "status": "queued",
  "title": "Escrow authorization queued",
  "message": "Awaiting multi-sig buyer confirmation in wallet console.",
  "reference": "ESC-001"
}
```

### Merchant console (Control Plane)
| Endpoint | Purpose |
|---|---|
| `GET /api/transactions` | Transaction list (feeds the Live Transaction Data Flow) |
| `GET /api/transactions/{txn_id}` | Full 10-step timeline for one transaction |
| `GET /api/connections` | 4 connection cards |
| `GET /api/health` | System Health panel |

`GET /api/transactions/TXN-001` — the UI renders **exactly** these steps:
```json
{
  "txn_id": "TXN-001",
  "quote_id": "Q-001",
  "status": "fulfilled",
  "decision": "ALLOW",
  "started_at": "2026-09-04T10:30:15Z",
  "ended_at": "2026-09-04T10:31:05Z",
  "duration_seconds": 50,
  "steps": [
    { "seq": 1,  "type": "user_request",      "title": "User request",        "timestamp": "2026-09-04T10:30:15Z", "description": "User asked to buy \"Nike Air Zoom Pegasus 40\" size 8", "status": "passed" },
    { "seq": 2,  "type": "buyer_agent",        "title": "AI Buyer Agent",      "timestamp": "2026-09-04T10:30:16Z", "description": "Buyer agent BA-001 received the request and started planning", "status": "passed" },
    { "seq": 3,  "type": "a2a_negotiation",    "title": "A2A negotiation",     "timestamp": "2026-09-04T10:30:18Z", "description": "Buyer agent negotiating with merchant agent via A2A protocol", "status": "passed" },
    { "seq": 4,  "type": "merchant_agent",     "title": "Merchant Agent",      "timestamp": "2026-09-04T10:30:22Z", "description": "Merchant agent MA-001 responded with product, price & availability", "status": "passed" },
    { "seq": 5,  "type": "quote_accepted",     "title": "Final quote accepted","timestamp": "2026-09-04T10:30:28Z", "description": "Quote Q-001 accepted by buyer agent", "status": "passed" },
    { "seq": 6,  "type": "payment_request",    "title": "Payment request",     "timestamp": "2026-09-04T10:30:30Z", "description": "Payment request sent to Paari Gateway", "status": "passed" },
    { "seq": 7,  "type": "governance",         "title": "Paari Governance",    "timestamp": "2026-09-04T10:30:31Z", "description": "All governance checks passed", "status": "passed", "decision": "ALLOW" },
    { "seq": 8,  "type": "payment_provider",   "title": "Razorpay payment",    "timestamp": "2026-09-04T10:30:33Z", "description": "Payment session created. Redirected to Razorpay", "status": "passed", "provider": "razorpay" },
    { "seq": 9,  "type": "payment_verified",   "title": "Payment verified",    "timestamp": "2026-09-04T10:31:02Z", "description": "Razorpay webhook verified. Payment captured successfully", "status": "passed" },
    { "seq": 10, "type": "fulfillment",        "title": "Merchant fulfilled",  "timestamp": "2026-09-04T10:31:05Z", "description": "Order created in Shopify. Fulfillment initiated.", "status": "fulfilled", "provider": "shopify", "payment_status": "success" }
  ]
}
```
**UI step-type → visual mapping (frontend-owned, backend just sends `type`):**
`governance` → emerald highlighted card (+ decision line); `payment_provider`
→ blue "/" Razorpay marker; `payment_verified` → emerald check; `fulfillment`
with `payment_status: "success"` → success card with "PAYMENT SUCCESSFUL"
footer. Unknown types render as normal steps, so extra steps are safe.

`GET /api/connections`
```json
{
  "connections": [
    { "id": "shopify", "name": "Shopify",   "status": "connected", "badge": "CONNECTED", "mode": "Live Store", "rows": { "store": "paari-demo-store", "webhook": "OK", "last_sync": "2 min ago" } },
    { "id": "razorpay","name": "Razorpay",  "status": "connected", "badge": "CONNECTED", "mode": "Test Mode",  "rows": { "mode": "Test", "webhook": "OK", "last_sync": "1 min ago" } },
    { "id": "a2a",     "name": "A2A Protocol", "status": "active", "rows": { "buyer_agents": "1", "merchant_agents": "1", "last_activity": "now" } },
    { "id": "llm",     "name": "LLM Service", "status": "ok", "model": "stepfun-3.7-flash", "rows": { "provider": "Nara Router", "status": "OK", "last_call": "5 sec ago" } }
  ]
}
```

`GET /api/health`
```json
{
  "status": "healthy",
  "metrics": {
    "services": { "online": 16, "total": 16, "label": "Online" },
    "webhooks":  { "ok": 4, "total": 4, "label": "Healthy" },
    "database":  { "status": "ok", "label": "SQLite" },
    "uptime":    { "percent": 99.9, "days": 30, "label": "30 days" }
  },
  "alerts": []          // non-empty → UI swaps "No active alerts" for the list
}
```

### Audit trail
| Endpoint | Purpose |
|---|---|
| `GET /api/audit/{txn_id}` | Full ledger page |

`GET /api/audit/TXN-001`
```json
{
  "txn_id": "TXN-001",
  "decision": "ALLOW",
  "checkpoints": { "passed": 10, "total": 10, "label": "Passed" },
  "duration_seconds": 50,
  "started_at": "2026-09-04T10:30:15Z",
  "ended_at": "2026-09-04T10:31:05Z",
  "status": "success",
  "status_note": "Fulfilled",
  "digest": "0x9d4b...83e1",
  "immutable": true,
  "steps": [ /* same shape as /api/transactions/{txn_id}.steps */ ]
}
```

**Timestamps:** send ISO 8601 UTC; the UI formats to local (it currently shows
`10:30:15 AM` style).

---

## 4. Auth

- **UI-side decision:** the web UI authenticates with a **JWT bearer token**
  obtained from `POST /api/auth/agent-token`, stored in localStorage, attached
  by a fetch wrapper (`Authorization: Bearer <jwt>`). If you prefer the
  `paari_session` httpOnly cookie route instead, the UI needs only
  `GET /api/auth/me` — say the word and we use that.
- Roles in the JWT/`/me` response: `buyer` | `merchant` | `operator`.
- Every endpoint below **requires** a valid token except `POST /api/auth/agent-token`.
- 401 → UI redirects to a login screen (to be built once auth exists).

---

## 5. Hosting / CORS

- **Dev ports today:** Next.js dev on **`http://localhost:3001`** (use 3001 —
  the default 3000 can collide with a stale server), FastAPI conventionally on
  `http://localhost:8000`.
- **Preferred wiring — same-origin proxy (no CORS):** Next.js `rewrites` in
  `next.config.ts`: `"/api/:path*" → "http://localhost:8000/api/:path*"`.
  The UI then just calls `fetch("/api/...")`. I will add this when we wire.
- **Fallback — CORS:** if you'd rather not proxy, enable CORS on FastAPI:
  `allow_origins=["http://localhost:3001"]`, `allow_credentials=true`,
  `allow_methods=["GET","POST","OPTIONS"]`,
  `allow_headers=["Authorization","Content-Type"]`.
- **Production:** same pattern — put the proxy/ingress in front of both, or a
  gateway (Caddy/Nginx/traefik). No hardcoded origins in the UI.

---

## 6. Error / REVIEW / DENY handling

Uniform error body on all non-2xx responses:
```json
{
  "error": {
    "code": "POLICY_DENIED",
    "message": "Purchase exceeds monthly budget ceiling",
    "details": { "decision": "DENY", "reason": "budget_exceeded", "limit": 45000, "requested": 60000 }
  }
}
```
Suggested HTTP mapping: 400 validation, 401 auth, 403 role/scope, 404
unknown txn/quote, 422 policy denial, 429 rate limit, 500 internal.

**Decision states on the buyer console** (the UI renders each differently):
- `ALLOW` → emerald settlement pane + "Sign & Escrow" (current look).
- `REVIEW` → amber/tertiary styling, show `error.message` + "Inspect Policy
  Limits" as the primary action; hide "Sign & Escrow".
- `DENY` → error-container styling (`#ffdad6`), no escrow action, show reason.
Same `decision` field drives the governance step on the merchant/audit pages.

---

## 7. Implementation order (suggested for backend)

1. **Auth:** `POST /api/auth/agent-token` + `GET /api/auth/me` (roles buyer/merchant/operator).
2. **Read paths:** `GET /api/health`, `GET /api/connections` (unblocks the merchant console instantly).
3. **Transactions:** `GET /api/transactions` + `GET /api/transactions/{txn_id}` (live data flow).
4. **Audit:** `GET /api/audit/{txn_id}` (reuses step data from #3).
5. **Buyer write paths:** `POST /api/agent/buyer/chat` + `POST /api/escrow/authorize` (+ REVIEW/DENY states).
6. **Polish:** `GET /api/policies/limits`, `GET /api/terms`.

Mock data the UI currently uses: `lib/txnSteps.ts` (10 steps) and inline JSX
(conversation, connections, health, audit summary). The UI will be rewired to
these endpoints once they exist — no UI redesign needed, only data plumbing.