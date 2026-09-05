Yes. Build **Paari as a policy-governed LLM/agent platform first**, without Shopify coupling. Then add Shopify as a **merchant environment adapter** that teaches the agent the store context and exposes controlled tools.

The clean architecture is:

```text
                    PAARI CORE
                       │
        ┌──────────────┼──────────────┐
        │              │              │
       LLM         Governance      Policy
        │              │              │
        │        Platform Rules   Merchant Rules
        │              │              │
        └──────────────┼──────────────┘
                       │
                Decision / Control
                       │
                Tool Permission
                       │
              ┌────────┴────────┐
              │                 │
        Later: Shopify      Later: Razorpay
```

# Phase 1 — Build the Paari Core LLM

Start with the LLM and its **operating contract**.

The LLM should understand:

```text
Who am I?
What is my role?
What actions can I take?
What actions are forbidden?
What information can I access?
When must I ask for approval?
How should I handle uncertainty?
```

Create a **Paari Agent System Prompt / Agent Constitution**.

Example:

```text
You are a Paari commerce agent.

You MUST:
- obey Paari platform governance
- obey merchant-specific policies
- use only authorized tools
- never bypass authorization
- never expose secrets
- never directly execute restricted financial actions
- request approval when required
- explain policy decisions
- record important transaction events

You MUST NOT:
- invent inventory
- invent prices
- override policy
- fabricate payment success
- access unauthorized data
```

This gives the LLM its behavioral foundation.

But this is **guidance**, not the final security mechanism.

---

# Phase 2 — Build the Governance Layer

Create a **Paari Global Governance Registry**.

```text
PAARI GOVERNANCE
│
├── Security
├── Agent identity
├── Authentication
├── Authorization
├── Privacy
├── Payment safety
├── Transaction limits
├── Audit
├── Fraud/risk
└── Escalation
```

Example:

```json
{
  "payment": {
    "payment_credentials_exposure": false,
    "payment_verification_required": true
  },
  "security": {
    "authentication_required": true,
    "authorization_required": true
  },
  "audit": {
    "transaction_logging_required": true
  }
}
```

These rules apply to **every merchant and every Paari agent**.

---

# Phase 3 — Build the Policy Engine

Don't put all rules in the LLM.

Create a separate engine:

```text
                 REQUEST
                    │
                    ▼
              Policy Engine
                    │
        ┌───────────┼───────────┐
        ▼           ▼           ▼
      ALLOW       REVIEW       DENY
```

A good structure is:

```text
Paari Global Policy
        ↓
Merchant Policy
        ↓
Store/Product Policy
        ↓
Transaction Policy
        ↓
Final Decision
```

For your first version you can implement this in Python.

Later move to **Open Policy Agent (OPA)** for policy-as-code.

---

# Phase 4 — Build Policy Context for the LLM

The LLM needs to **know the policy context** before planning.

Instead of putting every policy permanently in the system prompt, construct a runtime context:

```json
{
  "paari_rules": {
    "authentication_required": true,
    "audit_required": true,
    "payment_verification_required": true
  },

  "merchant_rules": {
    "max_order": 20000,
    "max_discount": 10,
    "max_quantity": 5
  }
}
```

Then:

```text
User/Buyer Request
       ↓
Context Builder
       ↓
LLM
       ↓
Proposed Action
```

This is better than fine-tuning the model to memorize rules.

---

# Phase 5 — Build the Authorization Engine

Separate:

**"What does the agent want to do?"**

from:

**"Is the agent allowed to do it?"**

Define capabilities:

```text
catalog.read
inventory.read
product.read
quote.create
deal.negotiate
checkout.request
payment.request
order.read
```

Then an agent receives a capability set:

```json
{
  "agent_id": "PAARI-AGENT-001",
  "capabilities": [
    "catalog.read",
    "inventory.read",
    "quote.create"
  ]
}
```

A request for:

```text
payment.request
```

is rejected if that capability isn't granted.

---

# Phase 6 — Build the Agent Runtime

Now connect the LLM to governance + policies + tools.

Use this loop:

```text
USER / BUYER AGENT
        ↓
      LLM
        ↓
   Intent / Plan
        ↓
Capability Check
        ↓
Policy Check
        ↓
Risk Check
        ↓
Tool Execution
        ↓
Tool Result
        ↓
      LLM
        ↓
Next Action
```

This is the actual **Paari Agent Runtime**.

---

# Phase 7 — Add a Tool Registry

This is extremely important for your later Shopify integration.

Create:

```text
PAARI TOOL REGISTRY

Tool
├── name
├── description
├── input schema
├── output schema
├── required capability
├── risk level
└── allowed systems
```

Example:

```json
{
  "name": "get_inventory",
  "required_capability": "inventory.read",
  "risk": "LOW",
  "system": "SHOPIFY"
}
```

Another:

```json
{
  "name": "request_payment",
  "required_capability": "payment.request",
  "risk": "HIGH",
  "system": "RAZORPAY"
}
```

Now your LLM doesn't receive arbitrary API access.

It receives **approved tools**.

---

# Phase 8 — Build the Tool Execution Gateway

Never:

```text
LLM → Shopify API
```

Instead:

```text
LLM
 ↓
Tool Request
 ↓
Paari Tool Gateway
 ↓
Authentication
 ↓
Authorization
 ↓
Policy
 ↓
Risk
 ↓
Tool
```

For example:

```text
LLM:
get_inventory(P001)

        ↓

Paari:
Does agent have inventory.read?

        ↓ YES

Paari:
Is this merchant allowed?

        ↓ YES

Paari:
Execute tool

        ↓

Shopify
```

This becomes your main security boundary.

---

# Phase 9 — Add Memory and State

Create two different types of memory.

### Long-term configuration

```text
Paari policies
Agent configuration
Merchant configuration
Tool permissions
```

### Runtime state

```text
Current buyer request
Current negotiation
Current quote
Current transaction
Current payment state
```

Don't use LLM memory as the source of truth for inventory/payment/order state.

Use your database.

Recommended:

```text
Supabase PostgreSQL
```

---

# Phase 10 — Add Decision / Risk Engine

Now introduce your probabilistic layer.

```text
                 ACTION
                   │
        ┌──────────┴──────────┐
        │                     │
 Deterministic            Probabilistic
 Policy Engine             Risk Engine
        │                     │
        │                fraud probability
        │                anomaly score
        │                agent trust
        │
        └──────────┬──────────┘
                   ▼
              FINAL DECISION
```

For example:

```text
Policy = ALLOW
Risk = 0.91 suspicious
        ↓
REVIEW
```

This is the right place to use ML/LLM-based risk reasoning.

---

# Phase 11 — Build the Audit Layer

Every action should produce an event.

```text
Agent requested action
        ↓
Authorization decision
        ↓
Policy decision
        ↓
Risk decision
        ↓
Tool executed
        ↓
Result
```

Store:

```json
{
  "request_id": "REQ-123",
  "agent_id": "AG-001",
  "action": "request_quote",
  "policy_version": "P-7",
  "decision": "ALLOW",
  "risk_score": 12,
  "timestamp": "..."
}
```

Now Paari can answer:

> **Why did the system allow or reject this action?**

---

# Phase 12 — Only now connect Shopify

Once Paari Core is stable, create:

## Shopify Adapter

```text
                PAARI
                  │
             Tool Registry
                  │
             Shopify Tools
                  │
            Shopify Adapter
                  │
               SHOPIFY
```

The Shopify adapter exposes tools such as:

```text
search_products()
get_product()
get_inventory()
get_price()
get_shipping_policy()
get_return_policy()
get_order_status()
```

Shopify's current agentic-commerce ecosystem supports UCP/MCP interfaces for agent-facing catalog, cart, checkout and related capabilities, so these can later become inputs/connectors for your Paari tool layer rather than requiring you to invent a completely separate commerce interface.

---

# Phase 13 — Teach Paari about the merchant store

When a merchant connects Shopify:

```text
Shopify
   ↓
Store Discovery
   ↓
Store Context Builder
   ↓
Paari Merchant Profile
```

Retrieve:

```text
Products
Inventory
Prices
Variants
Shipping
Returns
Store policies
Agent capabilities
```

Shopify also provides agent-facing store information through mechanisms such as `agents.md`, which can describe store capabilities and published policies.

Then create:

```text
MERCHANT CONTEXT
```

for that particular store.

---

# Phase 14 — Compile Shopify + Merchant + Paari policies

This is your key architecture.

```text
              PAARI POLICY
                   +
           MERCHANT POLICY
                   +
          SHOPIFY STORE POLICY
                   +
         PRODUCT CONSTRAINTS
                   ↓
            POLICY COMPILER
                   ↓
          EFFECTIVE POLICY
                   ↓
            MERCHANT AGENT
```

For example:

```text
Paari:
payment verification required

Merchant:
max order = ₹20,000

Shopify:
international shipping unavailable

Effective policy:
payment must be verified
order ≤ ₹20,000
international = unavailable
```

---

# Phase 15 — Merchant becomes AI-transactable

Now Paari can expose:

```text
Merchant ID
Store ID
Supported capabilities
Agent endpoint
Policies
Available tools
Transaction requirements
```

So an external Buyer Agent can discover:

```text
Merchant: ABC Snowboards
Status: AI-TRANSACTABLE

Capabilities:
✓ Search
✓ Inventory
✓ Deal
✓ Quote
✓ Checkout

Restrictions:
₹20,000 max autonomous transaction
```

---

# Phase 16 — Later connect Razorpay

Only after the above works.

```text
Buyer Agent
     ↓
Paari
     ↓
Quote
     ↓
Policy
     ↓
Authorization
     ↓
Payment Tool
     ↓
Razorpay
     ↓
Webhook
     ↓
Payment Verification
     ↓
Transaction
     ↓
Shopify Order
```

Razorpay's webhook system can provide payment state changes to your backend, where the signature should be verified before your transaction state is updated.

---

# The final Paari architecture

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

## And the learning model should be

Don't train one giant model on merchant data.

Instead:

```text
                    PAARI LLM
                        │
              ┌─────────┴─────────┐
              │                   │
      Paari Governance       Merchant Context
              │                   │
       Platform rules        Shopify data
       Global policies       Store policies
              │                   │
              └─────────┬─────────┘
                        ▼
                 Runtime Context
                        │
                        ▼
                    Tool Use
                        │
                        ▼
                  Policy Check
                        │
                        ▼
                    Execution
```

The **LLM learns/understands through context and tool results**, while the **policy engine enforces**.

### Best implementation sequence

```text
1. Paari LLM
       ↓
2. Paari Governance
       ↓
3. Policy Engine
       ↓
4. Authorization
       ↓
5. Tool Registry
       ↓
6. Tool Gateway
       ↓
7. Memory + State
       ↓
8. Risk Engine
       ↓
9. Audit
       ↓
10. Shopify Adapter
       ↓
11. Shopify Store Context
       ↓
12. Merchant Policies
       ↓
13. AI-transactable Merchant
       ↓
14. Razorpay
       ↓
15. End-to-end transaction
```

**This is the method I recommend:** build the **Paari brain + control plane first**, make it capable of safely deciding which tools it can use, and only then connect Shopify as a merchant-specific environment. That way Shopify becomes a **plugin to Paari**, rather than the foundation of Paari.

----

Yes. Build **Paari as a policy-governed LLM/agent platform first**, without Shopify coupling. Then add Shopify as a **merchant environment adapter** that teaches the agent the store context and exposes controlled tools.

The clean architecture is:

```text
                    PAARI CORE
                       │
        ┌──────────────┼──────────────┐
        │              │              │
       LLM         Governance      Policy
        │              │              │
        │        Platform Rules   Merchant Rules
        │              │              │
        └──────────────┼──────────────┘
                       │
                Decision / Control
                       │
                Tool Permission
                       │
              ┌────────┴────────┐
              │                 │
        Later: Shopify      Later: Razorpay
```

# Phase 1 — Build the Paari Core LLM

Start with the LLM and its **operating contract**.

The LLM should understand:

```text
Who am I?
What is my role?
What actions can I take?
What actions are forbidden?
What information can I access?
When must I ask for approval?
How should I handle uncertainty?
```

Create a **Paari Agent System Prompt / Agent Constitution**.

Example:

```text
You are a Paari commerce agent.

You MUST:
- obey Paari platform governance
- obey merchant-specific policies
- use only authorized tools
- never bypass authorization
- never expose secrets
- never directly execute restricted financial actions
- request approval when required
- explain policy decisions
- record important transaction events

You MUST NOT:
- invent inventory
- invent prices
- override policy
- fabricate payment success
- access unauthorized data
```

This gives the LLM its behavioral foundation.

But this is **guidance**, not the final security mechanism.

---

# Phase 2 — Build the Governance Layer

Create a **Paari Global Governance Registry**.

```text
PAARI GOVERNANCE
│
├── Security
├── Agent identity
├── Authentication
├── Authorization
├── Privacy
├── Payment safety
├── Transaction limits
├── Audit
├── Fraud/risk
└── Escalation
```

Example:

```json
{
  "payment": {
    "payment_credentials_exposure": false,
    "payment_verification_required": true
  },
  "security": {
    "authentication_required": true,
    "authorization_required": true
  },
  "audit": {
    "transaction_logging_required": true
  }
}
```

These rules apply to **every merchant and every Paari agent**.

---

# Phase 3 — Build the Policy Engine

Don't put all rules in the LLM.

Create a separate engine:

```text
                 REQUEST
                    │
                    ▼
              Policy Engine
                    │
        ┌───────────┼───────────┐
        ▼           ▼           ▼
      ALLOW       REVIEW       DENY
```

A good structure is:

```text
Paari Global Policy
        ↓
Merchant Policy
        ↓
Store/Product Policy
        ↓
Transaction Policy
        ↓
Final Decision
```

For your first version you can implement this in Python.

Later move to **Open Policy Agent (OPA)** for policy-as-code.

---

# Phase 4 — Build Policy Context for the LLM

The LLM needs to **know the policy context** before planning.

Instead of putting every policy permanently in the system prompt, construct a runtime context:

```json
{
  "paari_rules": {
    "authentication_required": true,
    "audit_required": true,
    "payment_verification_required": true
  },

  "merchant_rules": {
    "max_order": 20000,
    "max_discount": 10,
    "max_quantity": 5
  }
}
```

Then:

```text
User/Buyer Request
       ↓
Context Builder
       ↓
LLM
       ↓
Proposed Action
```

This is better than fine-tuning the model to memorize rules.

---

# Phase 5 — Build the Authorization Engine

Separate:

**"What does the agent want to do?"**

from:

**"Is the agent allowed to do it?"**

Define capabilities:

```text
catalog.read
inventory.read
product.read
quote.create
deal.negotiate
checkout.request
payment.request
order.read
```

Then an agent receives a capability set:

```json
{
  "agent_id": "PAARI-AGENT-001",
  "capabilities": [
    "catalog.read",
    "inventory.read",
    "quote.create"
  ]
}
```

A request for:

```text
payment.request
```

is rejected if that capability isn't granted.

---

# Phase 6 — Build the Agent Runtime

Now connect the LLM to governance + policies + tools.

Use this loop:

```text
USER / BUYER AGENT
        ↓
      LLM
        ↓
   Intent / Plan
        ↓
Capability Check
        ↓
Policy Check
        ↓
Risk Check
        ↓
Tool Execution
        ↓
Tool Result
        ↓
      LLM
        ↓
Next Action
```

This is the actual **Paari Agent Runtime**.

---

# Phase 7 — Add a Tool Registry

This is extremely important for your later Shopify integration.

Create:

```text
PAARI TOOL REGISTRY

Tool
├── name
├── description
├── input schema
├── output schema
├── required capability
├── risk level
└── allowed systems
```

Example:

```json
{
  "name": "get_inventory",
  "required_capability": "inventory.read",
  "risk": "LOW",
  "system": "SHOPIFY"
}
```

Another:

```json
{
  "name": "request_payment",
  "required_capability": "payment.request",
  "risk": "HIGH",
  "system": "RAZORPAY"
}
```

Now your LLM doesn't receive arbitrary API access.

It receives **approved tools**.

---

# Phase 8 — Build the Tool Execution Gateway

Never:

```text
LLM → Shopify API
```

Instead:

```text
LLM
 ↓
Tool Request
 ↓
Paari Tool Gateway
 ↓
Authentication
 ↓
Authorization
 ↓
Policy
 ↓
Risk
 ↓
Tool
```

For example:

```text
LLM:
get_inventory(P001)

        ↓

Paari:
Does agent have inventory.read?

        ↓ YES

Paari:
Is this merchant allowed?

        ↓ YES

Paari:
Execute tool

        ↓

Shopify
```

This becomes your main security boundary.

---

# Phase 9 — Add Memory and State

Create two different types of memory.

### Long-term configuration

```text
Paari policies
Agent configuration
Merchant configuration
Tool permissions
```

### Runtime state

```text
Current buyer request
Current negotiation
Current quote
Current transaction
Current payment state
```

Don't use LLM memory as the source of truth for inventory/payment/order state.

Use your database.

Recommended:

```text
Supabase PostgreSQL
```

---

# Phase 10 — Add Decision / Risk Engine

Now introduce your probabilistic layer.

```text
                 ACTION
                   │
        ┌──────────┴──────────┐
        │                     │
 Deterministic            Probabilistic
 Policy Engine             Risk Engine
        │                     │
        │                fraud probability
        │                anomaly score
        │                agent trust
        │
        └──────────┬──────────┘
                   ▼
              FINAL DECISION
```

For example:

```text
Policy = ALLOW
Risk = 0.91 suspicious
        ↓
REVIEW
```

This is the right place to use ML/LLM-based risk reasoning.

---

# Phase 11 — Build the Audit Layer

Every action should produce an event.

```text
Agent requested action
        ↓
Authorization decision
        ↓
Policy decision
        ↓
Risk decision
        ↓
Tool executed
        ↓
Result
```

Store:

```json
{
  "request_id": "REQ-123",
  "agent_id": "AG-001",
  "action": "request_quote",
  "policy_version": "P-7",
  "decision": "ALLOW",
  "risk_score": 12,
  "timestamp": "..."
}
```

Now Paari can answer:

> **Why did the system allow or reject this action?**

---

# Phase 12 — Only now connect Shopify

Once Paari Core is stable, create:

## Shopify Adapter

```text
                PAARI
                  │
             Tool Registry
                  │
             Shopify Tools
                  │
            Shopify Adapter
                  │
               SHOPIFY
```

The Shopify adapter exposes tools such as:

```text
search_products()
get_product()
get_inventory()
get_price()
get_shipping_policy()
get_return_policy()
get_order_status()
```

Shopify's current agentic-commerce ecosystem supports UCP/MCP interfaces for agent-facing catalog, cart, checkout and related capabilities, so these can later become inputs/connectors for your Paari tool layer rather than requiring you to invent a completely separate commerce interface.

---

# Phase 13 — Teach Paari about the merchant store

When a merchant connects Shopify:

```text
Shopify
   ↓
Store Discovery
   ↓
Store Context Builder
   ↓
Paari Merchant Profile
```

Retrieve:

```text
Products
Inventory
Prices
Variants
Shipping
Returns
Store policies
Agent capabilities
```

Shopify also provides agent-facing store information through mechanisms such as `agents.md`, which can describe store capabilities and published policies.

Then create:

```text
MERCHANT CONTEXT
```

for that particular store.

---

# Phase 14 — Compile Shopify + Merchant + Paari policies

This is your key architecture.

```text
              PAARI POLICY
                   +
           MERCHANT POLICY
                   +
          SHOPIFY STORE POLICY
                   +
         PRODUCT CONSTRAINTS
                   ↓
            POLICY COMPILER
                   ↓
          EFFECTIVE POLICY
                   ↓
            MERCHANT AGENT
```

For example:

```text
Paari:
payment verification required

Merchant:
max order = ₹20,000

Shopify:
international shipping unavailable

Effective policy:
payment must be verified
order ≤ ₹20,000
international = unavailable
```

---

# Phase 15 — Merchant becomes AI-transactable

Now Paari can expose:

```text
Merchant ID
Store ID
Supported capabilities
Agent endpoint
Policies
Available tools
Transaction requirements
```

So an external Buyer Agent can discover:

```text
Merchant: ABC Snowboards
Status: AI-TRANSACTABLE

Capabilities:
✓ Search
✓ Inventory
✓ Deal
✓ Quote
✓ Checkout

Restrictions:
₹20,000 max autonomous transaction
```

---

# Phase 16 — Later connect Razorpay

Only after the above works.

```text
Buyer Agent
     ↓
Paari
     ↓
Quote
     ↓
Policy
     ↓
Authorization
     ↓
Payment Tool
     ↓
Razorpay
     ↓
Webhook
     ↓
Payment Verification
     ↓
Transaction
     ↓
Shopify Order
```

Razorpay's webhook system can provide payment state changes to your backend, where the signature should be verified before your transaction state is updated.

---

# The final Paari architecture

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

## And the learning model should be

Don't train one giant model on merchant data.

Instead:

```text
                    PAARI LLM
                        │
              ┌─────────┴─────────┐
              │                   │
      Paari Governance       Merchant Context
              │                   │
       Platform rules        Shopify data
       Global policies       Store policies
              │                   │
              └─────────┬─────────┘
                        ▼
                 Runtime Context
                        │
                        ▼
                    Tool Use
                        │
                        ▼
                  Policy Check
                        │
                        ▼
                    Execution
```

The **LLM learns/understands through context and tool results**, while the **policy engine enforces**.

### Best implementation sequence

```text
1. Paari LLM
       ↓
2. Paari Governance
       ↓
3. Policy Engine
       ↓
4. Authorization
       ↓
5. Tool Registry
       ↓
6. Tool Gateway
       ↓
7. Memory + State
       ↓
8. Risk Engine
       ↓
9. Audit
       ↓
10. Shopify Adapter
       ↓
11. Shopify Store Context
       ↓
12. Merchant Policies
       ↓
13. AI-transactable Merchant
       ↓
14. Razorpay
       ↓
15. End-to-end transaction
```

**This is the method I recommend:** build the **Paari brain + control plane first**, make it capable of safely deciding which tools it can use, and only then connect Shopify as a merchant-specific environment. That way Shopify becomes a **plugin to Paari**, rather than the foundation of Paari.

-------------------------------------------------------

Yes. Since you already have `paari-demo-store.myshopify.com`, I would build this as **Shopify → Paari Store Adapter → Paari Agent/LLM**, rather than connecting the LLM directly to Shopify.

Shopify's current architecture supports exactly the primitives we need: authenticated Admin GraphQL API with scoped access, and a Storefront MCP server for agent-facing catalog/cart/policy operations. ([Shopify][1])

# Target architecture

```text
                 PAARI PLATFORM
                       │
                       ▼
                PAARI AGENT / LLM
                       │
                 Tool Gateway
                       │
          ┌────────────┴────────────┐
          │                         │
   Shopify Admin Adapter      Shopify MCP Adapter
          │                         │
          ▼                         ▼
    Admin GraphQL API         Storefront MCP
          │                         │
          └────────────┬────────────┘
                       ▼
                SHOPIFY STORE
```

The key security rule is:

> **LLM → Paari tools → authorization/policy → Shopify.**

Never:

> **LLM → Shopify credentials/API directly.**

Shopify access tokens are scoped credentials, and Shopify explicitly requires apps to authenticate and use approved access scopes. ([Shopify][1])

---

# Step 1 — Create the Paari Shopify App

Create a Shopify app for Paari using Shopify CLI.

Your app will eventually be installed/authorized by each merchant.

For the first MVP, your app needs access roughly around:

```text
Products
Inventory
Orders
Store configuration/policies
```

Shopify provides scopes such as:

```text
read_products
read_inventory
read_orders
write_orders
```

The exact scopes should be chosen from the GraphQL operations you actually use; Shopify recommends requesting only the permissions your app needs. ([Shopify][2])

---

# Step 2 — Connect your demo store

Your flow:

```text
Merchant
   ↓
Paari Dashboard
   ↓
"Connect Shopify"
   ↓
Shopify authorization
   ↓
Merchant approves scopes
   ↓
Paari callback
   ↓
STORE-001
```

For your current store:

```text
Merchant ID:
MER-001

Store ID:
STORE-001

Shopify domain:
paari-demo-store.myshopify.com
```

Once authorized, Paari stores the Shopify connection securely on the server.

Shopify's current app authentication returns an access token whose scopes determine what your app can access. ([Shopify][1])

---

# Step 3 — Build a Shopify Adapter

This is the most important implementation layer.

Create:

```text
backend/
  integrations/
    shopify/
      auth.py
      admin.py
      storefront.py
      products.py
      inventory.py
      orders.py
      policies.py
```

Your LLM should never know Shopify GraphQL details.

Instead give Paari clean internal functions:

```python
search_products(query)
get_product(product_id)
get_inventory(variant_id)
get_store_policy()
get_order(order_id)
create_order(...)
```

Internally these functions call Shopify.

---

# Step 4 — Separate read and write tools

Start with mostly read-only tools.

### Read tools

```text
search_catalog
get_product
get_variant
get_inventory
get_price
get_shipping_policy
get_return_policy
get_order_status
```

### High-risk write tools

```text
create_order
update_order
request_payment
cancel_order
refund
```

Don't expose the high-risk tools to the LLM until the governance layer is ready.

---

# Step 5 — Give the LLM a Tool Registry

Create:

```text
Paari Tool Registry
```

Example:

```json
{
  "name": "check_inventory",
  "description": "Returns current available inventory for a product variant",
  "risk_level": "LOW",
  "required_capability": "inventory.read",
  "merchant_scope": true,
  "audit_required": true
}
```

Another:

```json
{
  "name": "create_order",
  "description": "Creates an order after transaction authorization",
  "risk_level": "HIGH",
  "required_capability": "order.create",
  "policy_check_required": true,
  "payment_verification_required": true,
  "audit_required": true
}
```

Now the LLM knows **what tools exist**, but not how to bypass them.

---

# Step 6 — Build the Store Context

Paari needs to "understand" the merchant.

Don't train the LLM on the whole Shopify database.

Create a **Store Context Service**:

```text
Shopify
   ↓
Store Context Builder
   ↓
Merchant Store Profile
   ↓
LLM runtime context
```

Store:

```text
Store identity
Merchant identity
Currency
Products
Categories
Inventory
Shipping
Returns
Store policies
Supported commerce capabilities
```

But keep dynamic information dynamic.

For example:

```text
Inventory → query Shopify live
Price → query Shopify/live commerce state
Order status → query Shopify
```

Don't rely on an old LLM context for those.

---

# Step 7 — Read Shopify's agent-facing store information

This is particularly useful for your Paari concept.

Shopify currently provides a **Storefront MCP server** for a single merchant that exposes catalog capabilities such as:

```text
search_catalog
lookup_catalog
get_product
```

The Storefront MCP also covers shopping/cart/policy-oriented agent interactions. ([Shopify][3])

Each store has a store-specific MCP endpoint based on its domain. ([Shopify][4])

So your Paari connector can have:

```text
Shopify Admin API
+
Shopify Storefront MCP
```

with different responsibilities.

---

# Step 8 — Use Admin API for privileged merchant operations

Use the authenticated Admin GraphQL API for things such as:

```text
Products
Inventory
Orders
Merchant-side data
```

Shopify's Admin API requires an authenticated app access token, with the allowed operations controlled by the granted scopes. ([Shopify][1])

This becomes:

```text
Paari Tool
   ↓
Shopify Admin Adapter
   ↓
Admin GraphQL
```

---

# Step 9 — Use Storefront MCP for agent-facing commerce

For agent-style product discovery, use the Shopify Storefront MCP where appropriate:

```text
Paari
  ↓
Storefront MCP
  ↓
Shopify catalog/cart/policy capabilities
```

Shopify explicitly positions Storefront MCP for connecting an AI agent to a specific store's catalog and shopping functionality. ([Shopify][4])

This is useful because your Paari platform doesn't have to recreate Shopify's agent-facing catalog semantics.

---

# Step 10 — Build the Policy Learner

Now solve your "learn the store policies" problem.

Do this:

```text
Shopify Store Information
        ↓
Policy Extractor
        ↓
Normalized Policy
        ↓
Paari Policy Registry
```

For example:

```text
Shopify:
Return window = 30 days

Paari:
{
  "returns": {
    "window_days": 30
  }
}
```

Then add merchant-configured policies:

```text
Merchant:
Maximum AI purchase = ₹20,000
Maximum discount = 10%
```

And finally:

```text
Paari Policy
+
Merchant Policy
+
Shopify Constraint
        ↓
Effective Policy
```

---

# Step 11 — Don't let "learning" mean model training

This is important.

For your MVP:

```text
❌ Fine-tune LLM every time merchant changes policy

✅ Retrieve current store data
✅ Retrieve current policies
✅ Give them as structured context
✅ Enforce them through Policy Engine
```

So when the merchant changes:

```text
Max discount:
10% → 15%
```

you update the policy record.

You don't retrain the model.

---

# Step 12 — Build Paari's policy context

Before the LLM acts:

```json
{
  "merchant_id": "MER-001",
  "store_id": "STORE-001",
  "policies": {
    "max_autonomous_order": 20000,
    "max_discount": 10,
    "max_quantity": 5,
    "international_shipping": false
  },
  "capabilities": [
    "catalog.read",
    "inventory.read",
    "quote.create"
  ]
}
```

Now the LLM understands the operating boundaries.

But again:

> **Context tells the LLM the rules; the enforcement layer guarantees the rules.**

---

# Step 13 — Build the Paari Tool Gateway

Now connect everything.

```text
                    PAARI LLM
                        │
                        ▼
                   Tool Request
                        │
                        ▼
                TOOL GATEWAY
                        │
                ┌───────┼────────┐
                ▼       ▼        ▼
             AuthZ    Policy    Risk
                │       │        │
                └───────┼────────┘
                        ▼
                    Tool Call
                        │
                        ▼
                Shopify Adapter
                        │
                        ▼
                     Shopify
```

This is the **actual security boundary**.

---

# Step 14 — Test with your real store

Once connected, your first test should be:

### Buyer request

```text
"Show me all snowboards under ₹8,000."
```

LLM:

```text
search_catalog()
```

Paari:

```text
authenticate
authorize
policy check
```

Shopify:

```text
catalog search
```

Result returns to LLM.

---

# Step 15 — Test inventory

Buyer:

> "Is Nike Runner size 9 available?"

LLM:

```text
check_inventory()
```

Paari:

```text
Agent authorized?
Tool allowed?
Store allowed?
```

Shopify:

```text
InventoryLevel
```

Result:

```text
Available: 8
```

Shopify's Admin GraphQL API has dedicated inventory resources, and access can be restricted through `read_inventory`/`write_inventory`. ([Shopify][2])

---

# Step 16 — Test order status

After you eventually create an order:

```text
Buyer Agent
    ↓
get_order_status()
    ↓
Paari
    ↓
Shopify
```

For agentic orders, Shopify currently provides order webhooks so your system can receive committed order changes rather than constantly polling. Shopify also recommends using the latest full order payload as the source of truth for the order state. ([Shopify][5])

---

# Step 17 — Connect payment later

Once Shopify is working:

```text
Merchant Agent / Paari
          ↓
Quote
          ↓
Transaction
          ↓
Payment Service
          ↓
Razorpay
```

Then:

```text
Razorpay
    ↓
payment event
    ↓
Paari verification
    ↓
transaction = PAID
    ↓
Shopify order / fulfillment
```

This keeps payment separate from the Shopify connector.

---

# Final architecture you should build

```text
                          PAARI
                            │
                ┌───────────▼───────────┐
                │       PAARI LLM       │
                └───────────┬───────────┘
                            │
                       Tool Request
                            │
                ┌───────────▼───────────┐
                │    TOOL GATEWAY       │
                │                       │
                │ Authentication        │
                │ Authorization         │
                │ Governance             │
                │ Policy                │
                │ Risk                  │
                │ Audit                 │
                └───────────┬───────────┘
                            │
                   Approved Tool
                            │
             ┌──────────────┴──────────────┐
             │                             │
             ▼                             ▼
     SHOPIFY ADMIN ADAPTER        SHOPIFY MCP ADAPTER
             │                             │
             ▼                             ▼
      Admin GraphQL API            Storefront MCP
             │                             │
             └──────────────┬──────────────┘
                            ▼
                    SHOPIFY STORE
                            │
                  ┌─────────┼─────────┐
                  ▼         ▼         ▼
              Products   Inventory   Orders
                            │
                            ▼
                    PAARI STORE CONTEXT
                            │
                     Policy Registry
                            │
             ┌──────────────┴──────────────┐
             ▼                             ▼
       Paari Governance              Merchant Policies
```

## Build this first

For your actual `paari-demo-store`, the immediate implementation sequence should be:

**Shopify App → OAuth/authorization → Store ID → Shopify Connector → Product/Inventory tools → Store Context → Policy Registry → Tool Gateway → Paari LLM.**

At that point you will have the first important milestone:

> **“A Paari LLM can safely understand and operate a connected Shopify merchant through authorized, governed tools.”**

Then we add **Buyer Agent → A2A → Paari → Shopify**, followed by **Quote → Razorpay → Payment verification → Shopify Order**.

[1]: https://shopify.dev/docs/apps/build/authentication-authorization?utm_source=chatgpt.com "About app authentication"
[2]: https://shopify.dev/docs/apps/build/authentication-authorization/manage-access-scopes?utm_source=chatgpt.com "Manage access scopes"
[3]: https://shopify.dev/docs/agents/catalog/storefront-catalog?utm_source=chatgpt.com "Storefront Catalog MCP"
[4]: https://shopify.dev/docs/apps/build/storefront-mcp/servers/storefront?utm_source=chatgpt.com "Storefront MCP server"
[5]: https://shopify.dev/docs/agents/orders/order-webhooks?utm_source=chatgpt.com "Order webhooks"

--------------

Yes. For **Paari Agentic Commerce**, you should treat Razorpay Test Mode as the **payment execution/simulation layer**, while Paari owns the **agent authorization, policy governance, transaction limits, approval, audit trail, and decisioning**.

Razorpay Test Mode itself is a sandbox: test keys start with `rzp_test_`, transactions use simulated money, and Test/Live environments have separate credentials. ([Razorpay][1])

## 1. Your target architecture

```text
                         PAARI PLATFORM
┌──────────────────────────────────────────────────────────┐
│                                                          │
│  AI Buyer Agent                                          │
│       │                                                  │
│       ▼                                                  │
│  ┌──────────────────────┐                                │
│  │ Paari Agent Gateway  │                                │
│  └──────────┬───────────┘                                │
│             ▼                                            │
│  ┌─────────────────────────────┐                         │
│  │ Authentication              │                         │
│  │ Agent Identity              │                         │
│  │ Authorization               │                         │
│  │ Merchant Policy Check       │                         │
│  │ Spending Limit              │                         │
│  │ Human Approval / Escalation │                         │
│  └──────────────┬──────────────┘                         │
│                 ▼                                        │
│       Payment Orchestrator                               │
│                 │                                        │
│                 ▼                                        │
│       Create Razorpay Order                              │
│                 │                                        │
└─────────────────┼────────────────────────────────────────┘
                  │
                  ▼
        ┌───────────────────────┐
        │ Razorpay Test Mode    │
        │                       │
        │ API credentials       │
        │ Order                 │
        │ Checkout              │
        │ Test payment          │
        │ Payment status        │
        │ Signature verification│
        │ Webhooks              │
        └───────────┬───────────┘
                    │
                    ▼
             Payment Result
                    │
                    ▼
            Paari Audit Ledger
                    │
                    ▼
        Order fulfilled / failed
```

The critical design principle is:

> **Razorpay decides whether the simulated payment transaction succeeded; Paari decides whether the AI agent was allowed to initiate that transaction.**

---

# 2. First build: Razorpay Test Mode

Go to your Razorpay Dashboard and switch to **Test Mode**.

Then:

**Account & Settings → API Keys → Generate Key**

Razorpay states that Test Mode API keys can be generated without adding a website, and the secret is shown only when generated, so store it securely. ([Razorpay][2])

You will get:

```text
RAZORPAY_KEY_ID=rzp_test_xxxxxxxxx
RAZORPAY_KEY_SECRET=xxxxxxxxxxxxxxxx
```

Do **not** put the secret in frontend code. Razorpay APIs use Basic Authentication with `key_id:key_secret`. ([Razorpay][3])

Your environment file should look like:

```env
RAZORPAY_KEY_ID=rzp_test_xxxxxxxxx
RAZORPAY_KEY_SECRET=xxxxxxxxxxxxxxxx
RAZORPAY_WEBHOOK_SECRET=your_webhook_secret
```

---

# 3. Your Paari backend should sit between the agent and Razorpay

Do **not** design this as:

```text
AI Agent → Razorpay
```

Instead:

```text
AI Agent
   ↓
Paari Gateway
   ↓
Policy Engine
   ↓
Payment Authorization
   ↓
Razorpay
```

This is important for your project because the AI agent should never independently decide:

> "I will spend ₹20,000."

Instead Paari should evaluate:

```json
{
  "agent_id": "buyer_agent_001",
  "merchant_id": "merchant_abc",
  "order_value": 4999,
  "currency": "INR",
  "user_limit": 10000,
  "merchant_allowed": true,
  "requires_human_approval": false
}
```

Then Paari can return:

```json
{
  "authorized": true,
  "transaction_id": "txn_paari_001",
  "max_amount": 10000
}
```

Only after this should the payment orchestrator talk to Razorpay.

---

# 4. Create the Razorpay Order

Razorpay recommends creating an Order for every payment, on the server side. The returned `order_id` is then passed to Checkout and associates the payment with that order. ([Razorpay][4])

The endpoint is:

```http
POST https://api.razorpay.com/v1/orders
```

with Basic Auth using your Test API credentials. ([Razorpay][3])

Example:

```python
import os
import razorpay
from dotenv import load_dotenv

load_dotenv()

client = razorpay.Client(
    auth=(
        os.getenv("RAZORPAY_KEY_ID"),
        os.getenv("RAZORPAY_KEY_SECRET")
    )
)

order = client.order.create({
    "amount": 499900,
    "currency": "INR",
    "receipt": "paari_txn_001",
    "notes": {
        "paari_transaction_id": "txn_paari_001",
        "buyer_agent_id": "buyer_agent_001",
        "merchant_id": "merchant_abc"
    }
})

print(order)
```

Remember:

```text
₹4,999 = 499900 paise
```

Razorpay's Orders API uses the currency's smallest unit. ([Razorpay][4])

The resulting object will contain something like:

```json
{
  "id": "order_xxxxx",
  "amount": 499900,
  "currency": "INR",
  "status": "created"
}
```

---

# 5. Paari should create its own transaction record

Don't make Razorpay's `order_id` your only transaction identifier.

Create:

```text
Paari Transaction
        │
        ├── paari_transaction_id
        ├── buyer_agent_id
        ├── merchant_id
        ├── user_id
        ├── product_id
        ├── amount
        ├── currency
        ├── policy_decision
        ├── approval_status
        ├── razorpay_order_id
        ├── razorpay_payment_id
        ├── payment_status
        └── audit_events
```

Example:

```json
{
  "paari_transaction_id": "txn_001",
  "buyer_agent_id": "agent_123",
  "merchant_id": "merchant_456",
  "amount": 4999,
  "currency": "INR",
  "status": "AUTHORIZED_BY_PAARI",
  "razorpay_order_id": "order_xyz"
}
```

This makes your system auditable.

---

# 6. Checkout / payment simulation

Once your server creates:

```text
order_xyz
```

send that order ID to the checkout frontend.

Razorpay's standard Checkout flow uses:

```html
<script src="https://checkout.razorpay.com/v1/checkout.js"></script>
```

and supplies:

```javascript
const options = {
    key: "rzp_test_xxxxx",
    amount: 499900,
    currency: "INR",
    order_id: "order_xyz",
    name: "Paari Agentic Commerce",
    description: "Test purchase",

    handler: function (response) {
        console.log(response);
    }
};

const rzp = new Razorpay(options);
rzp.open();
```

Razorpay specifically recommends passing the server-created `order_id` into Checkout. ([Razorpay][4])

In Test Mode, this produces a **mock payment experience**, not an actual financial transaction. ([Razorpay][4])

---

# 7. Test payment methods

You can use Razorpay's provided test payment credentials.

For example, Razorpay currently documents test UPI IDs such as:

```text
success@razorpay
failure@razorpay
```

for simulating successful and failed UPI flows. ([Razorpay][5])

It also provides test cards specifically for Test Mode. ([Razorpay][6])

So your Paari test cases should include:

```text
Test Case 1
₹999
UPI
Success

Test Case 2
₹999
UPI
Failure

Test Case 3
₹4,999
Card
Success

Test Case 4
₹15,000
Card
Paari policy blocks transaction
```

That last scenario is particularly important because it tests **Paari governance**, not just Razorpay.

---

# 8. Payment result returned to Paari

After successful Checkout, Razorpay returns:

```json
{
  "razorpay_payment_id": "pay_xxxxx",
  "razorpay_order_id": "order_xxxxx",
  "razorpay_signature": "signature_xxxxx"
}
```

Razorpay documents these values as the information returned after successful payment and recommends sending them to your server. ([Razorpay][4])

So:

```text
Browser
   ↓
razorpay_payment_id
razorpay_order_id
razorpay_signature
   ↓
Paari Backend
```

Do **not** trust the frontend alone to declare:

```text
payment successful
```

---

# 9. Signature verification

This is one of the most important security steps.

Your backend should verify the Razorpay signature using your **Razorpay Key Secret**.

Conceptually:

```text
razorpay_order_id
        +
razorpay_payment_id
        ↓
HMAC SHA256
        ↓
compare with razorpay_signature
```

Example in Python:

```python
import hmac
import hashlib
import os

def verify_payment_signature(
    order_id,
    payment_id,
    signature
):
    key_secret = os.getenv("RAZORPAY_KEY_SECRET")

    message = f"{order_id}|{payment_id}"

    generated_signature = hmac.new(
        key_secret.encode(),
        message.encode(),
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(
        generated_signature,
        signature
    )
```

Then:

```python
valid = verify_payment_signature(
    razorpay_order_id,
    razorpay_payment_id,
    razorpay_signature
)

if valid:
    print("Payment signature verified")
else:
    print("INVALID PAYMENT")
```

This creates your first important security boundary:

```text
Frontend Result
      ↓
Cryptographic Verification
      ↓
Paari Trusts Payment Result
```

---

# 10. But signature verification is not the end

For Paari, I would use **two layers**:

```text
Layer 1
Checkout signature verification

        +

Layer 2
Server-side Razorpay payment/order verification
```

Razorpay itself recommends webhooks for asynchronous automation and API verification for critical user-facing confirmation when necessary. ([Razorpay][7])

So your system becomes:

```text
Checkout response
       ↓
Signature verification
       ↓
Razorpay API status check
       ↓
Webhook confirmation
       ↓
Paari transaction finalized
```

---

# 11. Payment status

Your Paari database should track its own state machine.

For example:

```text
CREATED
   ↓
POLICY_CHECKED
   ↓
AUTHORIZED
   ↓
RAZORPAY_ORDER_CREATED
   ↓
PAYMENT_INITIATED
   ↓
PAYMENT_AUTHORIZED
   ↓
PAYMENT_CAPTURED
   ↓
ORDER_PAID
   ↓
FULFILLMENT_ALLOWED
```

Failure path:

```text
PAYMENT_INITIATED
        ↓
PAYMENT_FAILED
        ↓
RECOVERY
        ↓
RETRY / NEW METHOD / HUMAN
```

This becomes very valuable for your **"every money action explainable, bounded and gated"** requirement.

---

# 12. Webhooks

Now create a Test Mode webhook.

Razorpay's Dashboard supports webhook configuration and webhook secrets for signature validation. Test-mode webhooks receive events generated by Test Mode transactions. ([Razorpay][8])

For Paari, I would initially subscribe to payment/order events such as:

```text
payment.authorized
payment.captured
payment.failed
order.paid
```

Razorpay documents that `payment.captured` and `order.paid` correspond to a captured payment and paid order. ([Razorpay][9])

Your endpoint:

```http
POST /webhooks/razorpay
```

Example architecture:

```text
Razorpay
    │
    │ webhook
    ▼
/webhooks/razorpay
    │
    ├── Verify webhook signature
    │
    ├── Check event ID / idempotency
    │
    ├── Update transaction
    │
    ├── Update audit log
    │
    └── Notify Paari Agent
```

---

# 13. Verify webhook signature

Razorpay sends a signature in:

```http
X-Razorpay-Signature
```

when a webhook secret is configured. Your server needs to validate that signature. ([Razorpay][8])

Conceptually:

```python
import hmac
import hashlib

def verify_webhook(payload: bytes, signature: str, secret: str):
    generated = hmac.new(
        secret.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(
        generated,
        signature
    )
```

Use the **raw request body** for webhook verification rather than reconstructing the JSON yourself.

---

# 14. Idempotency is extremely important for Paari

Imagine Razorpay sends:

```text
payment.captured
```

twice.

Your system must not do:

```text
capture event 1 → fulfill order
capture event 2 → fulfill order AGAIN
```

Instead:

```text
Webhook Event ID
       ↓
Have we processed this?
   /          \
 YES           NO
  ↓             ↓
Ignore       Process
```

Razorpay explicitly highlights idempotency and event ordering as important considerations for webhook handling. ([Razorpay][8])

Your database should therefore have something like:

```text
processed_webhook_events
------------------------
event_id
event_type
received_at
processed_at
status
```

---

# 15. This is where Paari becomes different from a normal Razorpay integration

A normal e-commerce application might simply do:

```text
Customer
   ↓
Checkout
   ↓
Razorpay
   ↓
Payment
```

Your Paari implementation should be:

```text
AI Buyer Agent
      ↓
Purchase Intent
      ↓
Paari Identity Verification
      ↓
Agent Authorization
      ↓
Merchant Policy Evaluation
      ↓
Spending Limit
      ↓
Risk Evaluation
      ↓
Human Approval?
      │
   ┌──┴──┐
   │     │
  Yes    No
   │     │
Approval │
   └──┬──┘
      ↓
Transaction Authorization
      ↓
Razorpay Order Creation
      ↓
Razorpay Test Checkout
      ↓
Test Payment
      ↓
Signature Verification
      ↓
Webhook Verification
      ↓
Payment Captured
      ↓
Paari Transaction Finalization
      ↓
Merchant Fulfillment
```

That distinction is central to your project.

---

# 16. Build these APIs in Paari

I recommend starting with these endpoints:

```text
POST /api/payment/authorize

POST /api/payment/create-order

POST /api/payment/verify

GET  /api/payment/status/{transaction_id}

POST /api/webhooks/razorpay
```

### `POST /api/payment/authorize`

Input:

```json
{
  "buyer_agent_id": "agent_001",
  "merchant_id": "merchant_001",
  "product_id": "snowboard_123",
  "amount": 4999,
  "currency": "INR"
}
```

Output:

```json
{
  "authorized": true,
  "transaction_id": "txn_001",
  "max_amount": 5000
}
```

### `POST /api/payment/create-order`

Output:

```json
{
  "transaction_id": "txn_001",
  "razorpay_order_id": "order_123",
  "amount": 499900,
  "currency": "INR"
}
```

### `POST /api/payment/verify`

Input:

```json
{
  "transaction_id": "txn_001",
  "razorpay_order_id": "order_123",
  "razorpay_payment_id": "pay_123",
  "razorpay_signature": "..."
}
```

Output:

```json
{
  "verified": true,
  "status": "payment_verified"
}
```

---

# 17. Your minimum database design

For the first prototype, create:

```text
agents
------
agent_id
agent_type
status
owner_id

merchants
---------
merchant_id
store_name
status

policies
--------
policy_id
merchant_id
max_transaction_amount
requires_approval
allowed_payment_methods

transactions
------------
transaction_id
agent_id
merchant_id
amount
currency
status
razorpay_order_id
razorpay_payment_id
created_at

payment_events
--------------
event_id
transaction_id
event_type
payload
processed_at

audit_logs
----------
audit_id
transaction_id
actor
action
decision
reason
timestamp
```

---

# 18. Your first complete test scenario

Use exactly this as your first Paari demo:

```text
User:
"Buy this snowboard for me under ₹5,000."

        ↓

AI Buyer Agent

        ↓

Paari checks:
✓ Agent authenticated
✓ Merchant authenticated
✓ Product exists
✓ Price = ₹4,999
✓ Limit = ₹5,000
✓ Merchant accepts agent
✓ Payment allowed
✓ No human approval needed

        ↓

Paari Authorization:
AUTHORIZED

        ↓

Razorpay Test Order:
order_xxxxx

        ↓

Test Checkout

        ↓

success@razorpay

        ↓

Razorpay returns:
payment_id
order_id
signature

        ↓

Paari verifies signature

        ↓

Razorpay webhook:
payment.captured

        ↓

Paari verifies webhook

        ↓

Transaction:
SUCCESS

        ↓

Merchant order:
FULFILLMENT_ALLOWED
```

Then demonstrate the governance case:

```text
User:
"Buy this ₹25,000 snowboard."

User limit:
₹5,000

        ↓

Paari Policy Engine

        ↓

BLOCKED

        ↓

Razorpay is NEVER called
```

That second flow is especially important in your presentation because it demonstrates that **Paari governs the AI agent rather than merely wrapping a payment API**.

---

## 19. What you should build now

Your Razorpay sandbox stack should be:

```text
                    PAARI
                      │
       ┌──────────────┴──────────────┐
       │                             │
 Agent Identity                 Policy Engine
       │                             │
       └──────────────┬──────────────┘
                      │
                Payment Service
                      │
          ┌───────────┴───────────┐
          │                       │
   Create Razorpay Order    Transaction DB
          │
          ▼
   Razorpay Test Checkout
          │
          ▼
    Test Payment Method
          │
          ▼
 Signature Verification
          │
          ▼
       Webhooks
          │
          ▼
   Payment State Machine
          │
          ▼
       Audit Ledger
```

Razorpay gives you the **sandbox payment infrastructure**; you build the **agent payment governance layer around it**. The Razorpay API base URL remains `https://api.razorpay.com/v1/`; Test Mode is selected by using Test API credentials rather than a separate sandbox URL. ([Razorpay][10])

### Recommended implementation stack for your prototype

```text
Frontend
React / Next.js

Backend
FastAPI (Python)

Database
PostgreSQL

Agent layer
Your Paari LLM + agent orchestrator

Payment
Razorpay Test Mode

Security
JWT + agent identity + policy engine
HMAC signature verification

Events
Razorpay Webhooks

Audit
PostgreSQL audit tables
```

The cleanest next step is to implement **one complete working transaction**: `AI agent → Paari authorization → Razorpay test order → Checkout → signature verification → webhook → transaction marked SUCCESS`. That gives you the core payment skeleton before connecting Shopify and the merchant-agent policy layer.

[1]: https://razorpay.com/docs/payments/quickstart/?utm_source=chatgpt.com "Quickstart Guide | Razorpay Docs"
[2]: https://razorpay.com/docs/payments/dashboard/account-settings/api-keys/?utm_source=chatgpt.com "API Keys Generator on Razorpay Dashboard | Razorpay Docs"
[3]: https://razorpay.com/docs/api/authentication/?utm_source=chatgpt.com "API Authentication | Razorpay Docs"
[4]: https://razorpay.com/docs/payments/payment-gateway/web-integration/standard/integration-steps/?utm_source=chatgpt.com "Standard Checkout - Integration Steps | Razorpay Payment Gateway | Razorpay Docs"
[5]: https://razorpay.com/docs/payments/payments/test-upi-details/?utm_source=chatgpt.com "Test UPI ID Details to Test Payment Flow | Razorpay Docs"
[6]: https://razorpay.com/docs/payments/payments/test-card-details/?preferred-country=IN&utm_source=chatgpt.com "Test Cards Details to Test Payments and Subscriptions | Razorpay Docs"
[7]: https://razorpay.com/docs/webhooks/?utm_source=chatgpt.com "About Webhooks | Razorpay Docs"
[8]: https://razorpay.com/docs/webhooks/validate-test/?utm_source=chatgpt.com "Validate and Test Webhooks | Razorpay Docs"
[9]: https://razorpay.com/docs/webhooks/payments/?utm_source=chatgpt.com "Payments Webhook Events | Razorpay Docs"
[10]: https://razorpay.com/docs/api/sandbox-setup/?utm_source=chatgpt.com "API Sandbox Setup | Razorpay Docs"

Razorpay Test Mode
├── Test API credentials
├── Order creation
├── Checkout/payment simulation
├── Test payment methods
├── Payment status
├── Signature verification
└── Webhooks/events

-------

Yes. Based on the architecture we have finalized, I would build **Paari Gateway + Governance as one controlled transaction platform**, with the Gateway handling external agent requests and the Governance Engine deciding whether those requests may proceed.

The key flow is:

```text
AI BUYER AGENT
      │
      │ A2A request
      ▼
┌─────────────────────┐
│   PAARI GATEWAY     │
│                     │
│ Agent authentication│
│ Request validation  │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ GOVERNANCE ENGINE   │
│                     │
│ Identity            │
│ Authorization       │
│ Merchant access     │
│ Quote validation    │
│ User policy         │
│ Merchant policy     │
│ Payment policy      │
│ Session             │
│ Capability          │
│ Risk                │
└──────────┬──────────┘
           │
      ALLOW / DENY / REVIEW
           │
           ▼
┌─────────────────────┐
│ PAYMENT ORCHESTRATOR│
│                     │
│ Razorpay            │
│ Payment verification│
└──────────┬──────────┘
           │
           ▼
     MERCHANT AGENT
           │
           ▼
        SHOPIFY
```

The Merchant Agent already has the store, policies, quote, payment and order responsibilities in your design. 

# Phase 1 — Define the responsibility boundary

First lock this down:

### Paari Gateway

Handles:

```text
External AI agents
A2A requests
Authentication
Request validation
Rate limiting
Routing
Transaction creation
Governance invocation
Payment session creation
Payment execution routing
Webhook intake
```

### Governance Engine

Handles:

```text
Identity
Authorization
Policy enforcement
Quote validation
Spending limits
Autonomous-payment rules
Session validation
Capability validation
Risk
Transaction state
ALLOW / DENY / REVIEW
```

### Payment service

Handles:

```text
Razorpay order
Payment initiation
Payment status
Webhook processing
Signature verification
Reconciliation
```

### Merchant Agent

Handles:

```text
Catalog
Inventory
Price
Negotiation
Merchant policy
Quote
Order
Fulfillment
```

This separation is important because your uploaded design already says the LLM should not directly call Shopify or Razorpay; the controlled runtime/tool gateway sits between them. 

---

# Phase 2 — Define your core data model

Before APIs, create these tables:

```text
users
agents
agent_credentials
agent_permissions

merchants
merchant_agents

policies
policy_versions

quotes
transactions

payment_sessions
payment_capabilities

payments
webhook_events

audit_events
```

The most important object is:

```text
TRANSACTION
```

Everything should connect to it.

```text
Transaction
 ├── buyer_agent
 ├── merchant_agent
 ├── quote
 ├── policy version
 ├── payment session
 ├── capability
 ├── Razorpay order
 ├── Razorpay payment
 └── audit events
```

---

# Phase 3 — Build Agent Identity

You need to answer:

> Who is this AI buyer?

Create:

```text
agent_id
owner_id
agent_type
status
credentials
permissions
created_at
```

Example:

```json
{
  "agent_id": "BA-001",
  "owner_id": "USER-001",
  "agent_type": "BUYER",
  "status": "ACTIVE"
}
```

Then build:

```text
POST /agents/register
POST /agents/authenticate
GET  /agents/{agent_id}
```

Do authentication before any transaction operation.

---

# Phase 4 — Build Authorization

Authentication:

> Is this actually BA-001?

Authorization:

> What can BA-001 do?

Start with capabilities such as:

```text
catalog.read
product.read
quote.request
quote.accept
payment.request
payment.execute
order.read
```

Your source already distinguishes read, commerce, and high-risk capabilities, with payment and order actions treated as high risk. 

Create:

```text
POST /authorization/check
```

Example:

```json
{
  "agent_id": "BA-001",
  "action": "payment.request",
  "resource": "TXN-001"
}
```

Result:

```json
{
  "allowed": true
}
```

---

# Phase 5 — Build Merchant Registry

Every merchant connected to Paari gets:

```text
merchant_id
store_id
merchant_agent_id
status
policy_version
capabilities
```

Example:

```text
MER-001
   ↓
MA-001
   ↓
Shopify Store S-001
```

Create:

```text
POST /merchants/register
GET  /merchants/{merchant_id}
GET  /merchants/{merchant_id}/policy
```

This lets Paari answer:

> Is this merchant eligible for agentic transactions?

---

# Phase 6 — Build Policy Engine

You have three main policy layers:

```text
Paari Policy
     +
User Policy
     +
Merchant Policy
     ↓
Effective Policy
```

### Paari policy

Non-negotiable:

```text
authentication required
authorization required
payment verification required
audit required
credential isolation
policy cannot be bypassed
```

These are consistent with the governance requirements already defined in your source. 

### User policy

Example:

```json
{
  "max_transaction": 5000,
  "daily_limit": 10000,
  "autonomous_payment": true,
  "confirmation_above": 3000
}
```

### Merchant policy

Example:

```json
{
  "max_order_value": 20000,
  "max_quantity": 5,
  "max_discount_percent": 10,
  "negotiation_enabled": true
}
```

Your source already defines these kinds of merchant constraints. 

---

# Phase 7 — Build the Quote Service

This is where your Buyer Agent + Merchant Agent finish their deal.

```text
AI Buyer
   ↕
Merchant Agent
   ↕
Negotiation
   ↓
FINAL QUOTE
   ↓
ACCEPTED
```

Quote contains:

```text
quote_id
transaction_id
buyer_agent_id
merchant_agent_id
items
subtotal
discount
tax
shipping
total
currency
expiry
policy_version
status
```

The source design explicitly uses a quote containing these transaction details and an expiry. 

---

# Phase 8 — Create the Transaction

When the Merchant Agent sends:

```text
PAYMENT_REQUEST
```

Paari creates:

```text
TXN-001
```

with:

```json
{
  "transaction_id": "TXN-001",
  "buyer_agent_id": "BA-001",
  "merchant_agent_id": "MA-001",
  "quote_id": "Q-001",
  "amount": 4799,
  "currency": "INR",
  "status": "GOVERNANCE_PENDING"
}
```

From here, the transaction becomes the authoritative record.

---

# Phase 9 — Build the Governance Evaluator

This is the heart of Paari.

Create:

```text
GovernanceEngine.evaluate(transaction)
```

Run checks in this order:

```text
1. Buyer agent exists
2. Buyer agent authenticated
3. Buyer authorization valid
4. Merchant exists
5. Merchant authorized
6. Quote exists
7. Quote belongs to this transaction
8. Quote accepted
9. Quote not expired
10. Amount matches quote
11. User spending limit passes
12. Merchant policy passes
13. Paari policy passes
14. Autonomous payment allowed
15. Session valid
16. Capability valid
17. Transaction state valid
18. Risk check
```

Then:

```text
ALLOW
DENY
REVIEW
```

---

# Phase 10 — Standardize every governance result

Every rule should return:

```json
{
  "check": "USER_SPENDING_LIMIT",
  "status": "PASS",
  "reason_code": "WITHIN_LIMIT",
  "details": {
    "transaction_amount": 4799,
    "maximum_allowed": 5000
  }
}
```

Failure:

```json
{
  "check": "USER_SPENDING_LIMIT",
  "status": "FAIL",
  "reason_code": "LIMIT_EXCEEDED",
  "details": {
    "transaction_amount": 7999,
    "maximum_allowed": 5000
  }
}
```

This becomes your audit and dashboard data.

---

# Phase 11 — Build the central Governance API

Start with:

```http
POST /governance/evaluate
```

Request:

```json
{
  "transaction_id": "TXN-001"
}
```

Response:

```json
{
  "transaction_id": "TXN-001",
  "decision": "ALLOW",

  "checks": {
    "agent_identity": "PASS",
    "agent_authorization": "PASS",
    "merchant_authorization": "PASS",
    "quote": "PASS",
    "amount": "PASS",
    "user_policy": "PASS",
    "merchant_policy": "PASS",
    "autonomous_payment": "PASS",
    "session": "PASS",
    "capability": "PASS"
  }
}
```

This should be your **first working Governance milestone**.

---

# Phase 12 — Build Payment Authorization

Next:

```http
POST /transactions/{id}/authorize-payment
```

Internal flow:

```text
Transaction
   ↓
Governance.evaluate()
   ↓
ALLOW?
 ├── NO → DENY
 ├── REVIEW → Human approval
 └── YES
      ↓
Create Payment Session
      ↓
Create One-Time Capability
      ↓
Return authorization
```

Example:

```json
{
  "transaction_id": "TXN-001",
  "payment_session_id": "PS-001",
  "capability_id": "CAP-001",
  "amount": 4799,
  "expires_at": "...",
  "status": "AUTHORIZED"
}
```

The bounded payment session/capability is already part of your intended architecture. 

---

# Phase 13 — Connect your existing Razorpay integration

Now the Gateway calls your existing payment layer.

```text
Paari Gateway
      ↓
Governance = ALLOW
      ↓
Payment Service
      ↓
Razorpay Test Mode
      ↓
Create Order
```

Critical rule:

```text
Razorpay amount
     =
Paari authorized amount
```

Never let an LLM-generated amount go directly to Razorpay.

---

# Phase 14 — Build Payment Reconciliation

Create:

```text
Paari TXN
      ↕
Razorpay Order
      ↕
Razorpay Payment
```

Check:

```text
amount
currency
order ID
transaction reference
merchant
payment status
```

Example:

```text
Paari:       ₹4,799
Razorpay:    ₹4,799
             ↓
            PASS
```

But:

```text
Paari:       ₹4,799
Razorpay:    ₹7,999
             ↓
            BLOCK
```

---

# Phase 15 — Build Razorpay Webhook Verification

Flow:

```text
Razorpay
   ↓
Paari Webhook Gateway
   ↓
Verify authenticity
   ↓
Find Paari transaction
   ↓
Match Razorpay order
   ↓
Verify payment
   ↓
Update transaction
```

The source architecture likewise places payment verification before fulfillment. 

---

# Phase 16 — Build Fulfillment Authorization

Only:

```text
PAYMENT_VERIFIED
```

can produce:

```text
FULFILLMENT_AUTHORIZED
```

Then:

```text
Paari
  ↓
Merchant Agent
  ↓
Shopify
  ↓
Order
```

Never:

```text
Payment request
    ↓
Shopify order
```

---

# Phase 17 — Build the transaction state machine

Use:

```text
CREATED
   ↓
GOVERNANCE_PENDING
   ↓
AUTHORIZED
   ↓
PAYMENT_PENDING
   ↓
PAYMENT_VERIFICATION
   ↓
PAYMENT_CONFIRMED
   ↓
FULFILLMENT_AUTHORIZED
   ↓
FULFILLED
```

Failures:

```text
DENIED
REVIEW
EXPIRED
PAYMENT_FAILED
PAYMENT_REJECTED
RISK_BLOCKED
```

This prevents agents from randomly jumping from one state to another.

Your source has a very similar transaction progression. 

---

# Phase 18 — Build Audit

Everything gets an event:

```text
AGENT_AUTHENTICATED
AUTHORIZATION_PASSED
MERCHANT_VERIFIED
QUOTE_ACCEPTED
GOVERNANCE_PASSED
PAYMENT_SESSION_CREATED
RAZORPAY_ORDER_CREATED
PAYMENT_RECEIVED
PAYMENT_VERIFIED
FULFILLMENT_AUTHORIZED
ORDER_CREATED
```

Store:

```text
event_id
transaction_id
agent_id
merchant_id
event_type
decision
reason_code
policy_version
timestamp
```

---

# Phase 19 — Put Paari LLM on top

Only after Governance works deterministically.

The LLM consumes:

```text
governance decision
audit events
transaction data
policy facts
```

and produces:

```text
"Payment approved because the buyer agent was authorized,
the merchant was trusted, the quote was valid, and the
₹4,799 transaction was within the user's ₹5,000 autonomous limit."
```

So:

```text
LLM = explanation + semantic intelligence

Governance = authority

Razorpay = payment execution

Shopify = merchant execution
```

---

# Phase 20 — Final Paari Gateway API surface

Once v1 is complete, you should have roughly:

```text
AGENTS

POST /agents/register
POST /agents/authenticate
GET  /agents/{id}


MERCHANTS

POST /merchants/register
GET  /merchants/{id}


A2A

POST /a2a/message
POST /a2a/payment-request


TRANSACTIONS

POST /transactions
GET  /transactions/{id}


GOVERNANCE

POST /governance/evaluate
POST /transactions/{id}/authorize-payment


PAYMENTS

POST /payment-sessions
POST /payments/create
GET  /payments/{id}


RAZORPAY

POST /webhooks/razorpay


FULFILLMENT

POST /transactions/{id}/authorize-fulfillment


AUDIT

GET /transactions/{id}/audit
```

---

# The entire build roadmap

```text
                    PAARI V1
                       │
                       ▼
              ┌─────────────────┐
              │ Agent Identity  │
              └────────┬────────┘
                       ▼
                 Agent AuthZ
                       ▼
               Merchant Registry
                       ▼
                  Policy Engine
                       ▼
                 Quote Service
                       ▼
               Transaction Engine
                       ▼
              Governance Evaluator
                       ▼
            Payment Session/Capability
                       ▼
                Razorpay Adapter
                       ▼
             Payment Verification
                       ▼
             Fulfillment Authorization
                       ▼
                   Audit Log
                       ▼
              Paari LLM Explanation
```

### The most important MVP

Don't try to build the whole platform first.

Get this one path working:

```text
AI Buyer Agent
      ↓
Merchant Agent
      ↓
FINAL QUOTE
      ↓
PAYMENT REQUEST
      ↓
PAARI GATEWAY
      ↓
GOVERNANCE ENGINE
      ↓
ALLOW
      ↓
PAYMENT SESSION
      ↓
RAZORPAY TEST ORDER
      ↓
PAYMENT
      ↓
WEBHOOK
      ↓
VERIFICATION
      ↓
FULFILLMENT AUTHORIZATION
      ↓
SHOPIFY ORDER
      ↓
AUDIT TRAIL
```

Then deliberately demonstrate the opposite:

```text
AI Buyer
   ↓
Merchant Quote = ₹7,999
   ↓
Paari User Limit = ₹5,000
   ↓
GOVERNANCE
   ↓
DENY
   ↓
NO RAZORPAY PAYMENT
   ↓
NO SHOPIFY FULFILLMENT
   ↓
AUDIT: LIMIT_EXCEEDED
```

**That success + denial pair is the first real proof that Paari has made a merchant AI-transactable with governed agentic payments.**

Yes. **Focus only on the Paari Governance Gateway/Engine first.** Do not connect Shopify, Razorpay, Buyer Agent, Merchant Agent, or the LLM yet.

Your development sequence should be:

```text
1. Build individual governance components
              ↓
2. Connect the components
              ↓
3. Build the governance data flow
              ↓
4. Build the Gateway API
              ↓
5. Test ALLOW / DENY / REVIEW cases
```

# 1. Paari Governance Gateway — scope

For this phase, build only:

```text
                 PAARI GOVERNANCE GATEWAY
                           │
              ┌────────────┴────────────┐
              │                         │
        REQUEST VALIDATION         GOVERNANCE ENGINE
                                        │
        ┌───────────────────────────────┼────────────────┐
        │               │               │                │
     Identity        AuthZ           Policies        Transaction
        │               │               │                │
        │               │        ┌──────┴──────┐         │
        │               │        │             │         │
        │               │      Paari          User      Merchant
        │               │      Policy        Policy     Policy
        │               │        │             │         │
        └───────────────┴────────┴─────────────┴─────────┘
                                        │
                                   Decision Engine
                                        │
                               ALLOW / DENY / REVIEW
                                        │
                                  Audit / Decision
```

---

# 2. Component 1 — Governance Request

Everything entering Paari must first become a standard request.

Create:

```json
{
  "request_id": "REQ-001",
  "transaction_id": "TXN-001",

  "agent_id": "BA-001",
  "agent_type": "BUYER",

  "merchant_id": "MER-001",
  "merchant_agent_id": "MA-001",

  "action": "PAYMENT",

  "amount": 4900,
  "currency": "INR",

  "timestamp": "..."
}
```

For now this is just a test object.

Later your real AI Buyer Agent / Merchant Agent will produce it.

---

# 3. Component 2 — Agent Identity

Build an in-memory or database-backed registry.

```text
Agent
├── agent_id
├── owner_id
├── type
├── status
├── credential_status
└── permissions
```

Example:

```json
{
  "agent_id": "BA-001",
  "owner_id": "USER-001",
  "type": "BUYER",
  "status": "ACTIVE",
  "permissions": [
    "payment.request"
  ]
}
```

Your first functions:

```python
get_agent(agent_id)
is_agent_active(agent)
```

---

# 4. Component 3 — Agent Authorization

This answers:

> Is this agent allowed to perform this action?

Example:

```python
def check_authorization(agent, action):
    return action in agent.permissions
```

Test:

```text
BA-001
payment.request
       ↓
PASS
```

And:

```text
BA-002
payment.execute
       ↓
FAIL
```

Keep **identity** and **authorization** as separate modules.

---

# 5. Component 4 — Merchant Authorization

Even though you aren't connecting merchants yet, create the governance object.

```json
{
  "merchant_id": "MER-001",
  "merchant_agent_id": "MA-001",
  "status": "ACTIVE",
  "agent_transactions_enabled": true
}
```

Check:

```python
def check_merchant(merchant):
    return (
        merchant.status == "ACTIVE"
        and merchant.agent_transactions_enabled
    )
```

Later the real Merchant Registry plugs into this.

---

# 6. Component 5 — Quote / Agreement Policy

For this phase, don't build negotiation.

Just represent an already-agreed transaction.

```json
{
  "quote_id": "QUOTE-001",
  "transaction_id": "TXN-001",

  "buyer_agent_id": "BA-001",
  "merchant_agent_id": "MA-001",

  "amount": 4900,
  "currency": "INR",

  "status": "ACCEPTED",

  "expires_at": "..."
}
```

Your Governance Engine should check:

```text
Quote exists?
Quote accepted?
Quote belongs to transaction?
Buyer matches?
Merchant matches?
Not expired?
```

---

# 7. Component 6 — Paari Policies

These are the platform-level policies.

Create something like:

```json
{
  "policy_version": "PAARI-1",

  "authentication_required": true,
  "authorization_required": true,

  "payment_verification_required": true,

  "audit_required": true,

  "credential_isolation": true,

  "policy_bypass_allowed": false
}
```

These should be **mandatory**.

The source architecture similarly identifies authentication, authorization, credential isolation, audit, payment verification, spending controls, risk checks, and policy non-bypass as Paari governance controls. 

---

# 8. Component 7 — User Policies

Create a user-policy object even before connecting the real user system.

```json
{
  "user_id": "USER-001",

  "max_transaction_amount": 5000,

  "daily_spending_limit": 10000,

  "autonomous_payment": true,

  "confirmation_threshold": 3000
}
```

Governance checks:

```text
transaction <= max transaction?
daily total <= daily limit?
autonomous payment allowed?
human confirmation required?
```

---

# 9. Component 8 — Merchant Policies

Again, don't connect Shopify yet.

Just create the policy model:

```json
{
  "merchant_id": "MER-001",

  "max_order_value": 20000,
  "max_quantity": 5,

  "max_discount_percent": 10,

  "agent_transactions_enabled": true
}
```

The source design identifies merchant constraints such as maximum order, quantity, discount, allowed products, shipping countries, approval thresholds and negotiation rules. 

For Governance v1, implement only the rules needed for payment authorization.

---

# 10. Component 9 — Effective Policy

Now combine them:

```text
Paari Policy
      +
User Policy
      +
Merchant Policy
      ↓
Effective Policy
```

Example:

```text
Paari maximum = ₹10,000
User maximum = ₹5,000
Merchant maximum = ₹8,000
```

Effective maximum:

```text
₹5,000
```

Implement:

```python
def calculate_effective_limit(paari, user, merchant):
    return min(
        paari.max_transaction_amount,
        user.max_transaction_amount,
        merchant.max_order_value
    )
```

---

# 11. Component 10 — Transaction Model

Create the central object:

```json
{
  "transaction_id": "TXN-001",

  "buyer_agent_id": "BA-001",
  "merchant_agent_id": "MA-001",

  "quote_id": "QUOTE-001",

  "amount": 4900,
  "currency": "INR",

  "status": "GOVERNANCE_PENDING"
}
```

This is the object Governance evaluates.

---

# 12. Component 11 — Payment Session Policy

You don't need Razorpay yet.

Just create the concept.

```json
{
  "session_id": "PS-001",

  "transaction_id": "TXN-001",

  "authorized_amount": 4900,

  "status": "ACTIVE",

  "expires_at": "..."
}
```

Checks:

```text
Session exists
Session active
Session not expired
Amount within session amount
Transaction matches
```

---

# 13. Component 12 — Payment Capability

Create a one-time authorization capability:

```json
{
  "capability_id": "CAP-001",

  "transaction_id": "TXN-001",

  "action": "payment.execute",

  "max_amount": 4900,

  "usage": "ONE_TIME",

  "used": false
}
```

Checks:

```text
Capability exists?
Correct transaction?
Correct action?
Amount <= max amount?
Already used?
```

No actual payment happens here.

---

# 14. Component 13 — Governance Rules

Now create your actual rules.

I recommend putting them into independent functions.

```text
rules/
├── agent_identity.py
├── agent_authorization.py
├── merchant_authorization.py
├── quote_validation.py
├── amount_policy.py
├── user_spending.py
├── autonomous_payment.py
├── session_validation.py
└── capability_validation.py
```

Each rule returns the same structure:

```json
{
  "check": "USER_SPENDING_LIMIT",
  "status": "PASS",
  "reason_code": "WITHIN_LIMIT"
}
```

or:

```json
{
  "check": "USER_SPENDING_LIMIT",
  "status": "FAIL",
  "reason_code": "LIMIT_EXCEEDED"
}
```

---

# 15. Component 14 — Decision Engine

Now connect the rules.

```python
def evaluate(context):

    checks = [
        check_agent_identity(context),
        check_agent_authorization(context),
        check_merchant_authorization(context),
        check_quote(context),
        check_amount(context),
        check_user_spending(context),
        check_autonomous_payment(context),
        check_session(context),
        check_capability(context)
    ]

    failures = [
        check for check in checks
        if check["status"] == "FAIL"
    ]

    if failures:
        return {
            "decision": "DENY",
            "checks": checks
        }

    return {
        "decision": "ALLOW",
        "checks": checks
    }
```

Later add `REVIEW`.

---

# 16. Don't let one rule overwrite another

Suppose:

```text
Agent = valid
Merchant = valid
Quote = valid
Amount = ₹4,900
User limit = ₹5,000
Autonomous payment = false
```

The final result should be:

```text
REVIEW
```

not:

```text
ALLOW
```

So use a decision priority:

```text
DENY
  ↓
REVIEW
  ↓
ALLOW
```

Meaning:

```text
Any mandatory failure → DENY

No failure but human approval required → REVIEW

Everything passes → ALLOW
```

---

# 17. Component 15 — Transaction State Machine

Even without payments, implement the state machine.

```text
CREATED
   ↓
GOVERNANCE_PENDING
   ↓
AUTHORIZED
```

Failure:

```text
DENIED
```

Review:

```text
REVIEW_REQUIRED
```

Expired:

```text
EXPIRED
```

This ensures your Gateway knows what state a transaction is in.

---

# 18. Component 16 — Audit Logger

Every check should produce an audit event.

```json
{
  "event_id": "EVT-001",
  "request_id": "REQ-001",
  "transaction_id": "TXN-001",

  "event_type": "GOVERNANCE_CHECK",

  "check": "USER_SPENDING_LIMIT",

  "result": "PASS",

  "reason_code": "WITHIN_LIMIT",

  "timestamp": "..."
}
```

Then the final event:

```json
{
  "event_type": "GOVERNANCE_DECISION",
  "decision": "ALLOW",
  "transaction_id": "TXN-001"
}
```

Your uploaded design also treats the audit trail as a first-class component of the transaction lifecycle. 

---

# 19. Only now build the Gateway

Once all individual components work, expose one external API:

```http
POST /gateway/governance/evaluate
```

Input:

```json
{
  "request_id": "REQ-001",
  "transaction_id": "TXN-001"
}
```

Internally:

```text
Gateway
   ↓
Load Transaction
   ↓
Load Agent
   ↓
Load Merchant
   ↓
Load Quote
   ↓
Load Policies
   ↓
Build Governance Context
   ↓
Governance Engine
   ↓
Decision
   ↓
Audit
   ↓
Response
```

---

# 20. Gateway response

Successful:

```json
{
  "request_id": "REQ-001",
  "transaction_id": "TXN-001",

  "decision": "ALLOW",

  "checks": {
    "agent_identity": "PASS",
    "agent_authorization": "PASS",
    "merchant_authorization": "PASS",
    "quote": "PASS",
    "amount": "PASS",
    "user_policy": "PASS",
    "merchant_policy": "PASS",
    "autonomous_payment": "PASS",
    "session": "PASS",
    "capability": "PASS"
  }
}
```

Failure:

```json
{
  "request_id": "REQ-002",
  "transaction_id": "TXN-002",

  "decision": "DENY",

  "failed_checks": [
    {
      "check": "USER_SPENDING_LIMIT",
      "reason_code": "LIMIT_EXCEEDED"
    }
  ]
}
```

---

# 21. Your build process should be exactly this

## Stage A — Individual pieces

Build independently:

```text
Agent Identity
       ↓
Authorization
       ↓
Merchant Registry
       ↓
Policy Models
       ↓
Quote Model
       ↓
Transaction Model
       ↓
Session Model
       ↓
Capability Model
       ↓
Audit Model
```

Test each independently.

---

## Stage B — Connect pieces

Connect:

```text
Agent
  +
Merchant
  +
Quote
  +
Transaction
  +
Policies
  +
Session
  +
Capability
```

into:

```text
GovernanceContext
```

Example:

```python
context = GovernanceContext(
    agent=agent,
    merchant=merchant,
    quote=quote,
    transaction=transaction,
    paari_policy=paari_policy,
    user_policy=user_policy,
    merchant_policy=merchant_policy,
    session=session,
    capability=capability
)
```

---

## Stage C — Data flow

Build:

```text
REQUEST
   ↓
VALIDATE
   ↓
LOAD CONTEXT
   ↓
RUN RULES
   ↓
AGGREGATE RESULTS
   ↓
DECISION
   ↓
UPDATE TRANSACTION
   ↓
AUDIT
   ↓
RESPONSE
```

---

## Stage D — Gateway

Expose:

```text
POST /gateway/governance/evaluate
```

Initially, **nothing external calls it**.

You can use Postman/curl to simulate agents.

---

# 22. Testing matrix

Before connecting anything else, test these cases.

| Test                              | Expected |
| --------------------------------- | -------- |
| Valid agent + valid policies      | ALLOW    |
| Unknown agent                     | DENY     |
| Inactive agent                    | DENY     |
| Missing payment permission        | DENY     |
| Unauthorized merchant             | DENY     |
| Expired quote                     | DENY     |
| Quote amount ≠ transaction amount | DENY     |
| Amount > user limit               | DENY     |
| Amount > merchant limit           | DENY     |
| Autonomous payment disabled       | REVIEW   |
| Expired session                   | DENY     |
| Capability already used           | DENY     |
| Wrong transaction capability      | DENY     |
| Everything valid                  | ALLOW    |

This is the foundation you should finish **before connecting your Buyer Agent, Merchant Agent, Shopify, or Razorpay**.

---

# 23. Final isolated Paari Governance Engine

At this stage your system is simply:

```text
                TEST REQUEST
                     │
                     ▼
             PAARI GATEWAY
                     │
                     ▼
           ┌─────────────────┐
           │ GOVERNANCE      │
           │ ENGINE          │
           └────────┬────────┘
                    │
       ┌────────────┼─────────────┐
       │            │             │
     Agent        Merchant      Policy
     checks       checks        checks
       │            │             │
       └────────────┼─────────────┘
                    │
              Transaction
                 checks
                    │
                    ▼
           ┌────────────────┐
           │ DECISION ENGINE│
           └───────┬────────┘
                   │
          ┌────────┼────────┐
          ▼        ▼        ▼
       ALLOW     REVIEW    DENY
          │        │        │
          └────────┼────────┘
                   ▼
               AUDIT LOG
```

### What you should **not** build yet

```text
❌ Razorpay connection
❌ Shopify connection
❌ Buyer Agent
❌ Merchant Agent
❌ LLM
❌ A2A network
❌ Negotiation
❌ Real payment
```

Those come **after this engine passes its own tests**.

Your first concrete milestone is therefore:

> **Build a standalone Paari Governance Gateway that accepts a simulated transaction, loads simulated agent/merchant/quote/policy/session/capability data, evaluates every governance rule, returns ALLOW/DENY/REVIEW, updates transaction state, and writes a complete audit trail.**

That gives you a clean, independently testable **Paari governance core** before you connect any other system.

----------

Yes. For **Phase 1**, keep the architecture extremely focused on one thing:

> **Merchant Agent creates the final quotation + payment request → Paari Governance Gateway validates the transaction → Paari Payment Service creates/handles the Razorpay payment flow → payment result comes back through Paari → Merchant Agent continues the order.**

Do **not** introduce A2A yet. Phase 2 will add standardized agent-to-agent communication around this already-working transaction core.

# Phase 1 architecture

```text id="4h9u1k"
                  PHASE 1

            MERCHANT AGENT
                  │
                  │
        Final Quote + Payment Request
                  │
                  ▼
        ┌─────────────────────┐
        │ PAARI GOVERNANCE    │
        │       GATEWAY       │
        │                     │
        │ Authentication      │
        │ Authorization       │
        │ Paari Policies      │
        │ Merchant Policies   │
        │ Risk Checks         │
        │ Amount Validation   │
        │ Audit               │
        └──────────┬──────────┘
                   │
             APPROVED REQUEST
                   │
                   ▼
        ┌─────────────────────┐
        │ PAARI PAYMENT       │
        │      SERVICE        │
        └──────────┬──────────┘
                   │
                   ▼
              RAZORPAY
                   │
          Test Payment Flow
                   │
                   ▼
        Payment Result/Webhook
                   │
                   ▼
        PAARI PAYMENT SERVICE
                   │
                   ▼
          GOVERNANCE GATEWAY
                   │
             VERIFIED
                   │
                   ▼
            MERCHANT AGENT
                   │
                   ▼
             ORDER/FULFILL
```

## 1. Merchant Agent prepares the deal

For Phase 1, assume the Merchant Agent already knows the store/product information.

It produces:

```json id="m1j5y6"
{
  "transaction_id": "TXN-001",
  "merchant_agent_id": "MA-001",
  "quote_id": "Q-001",
  "product_id": "P001",
  "quantity": 1,
  "subtotal": 7500,
  "discount": 500,
  "shipping": 0,
  "total": 7000,
  "currency": "INR"
}
```

Then it sends:

```text id="c1ec7h"
QUOTE + PAYMENT REQUEST
        ↓
PAARI GOVERNANCE GATEWAY
```

This is the key Phase-1 message.

---

# 2. Paari Governance Gateway receives it

The Gateway should **not immediately call Razorpay**.

First it checks:

```text id="ve1o7j"
1. Is Merchant Agent valid?
2. Is Merchant Agent active?
3. Is transaction valid?
4. Is quote valid?
5. Is quote expired?
6. Is amount correct?
7. Does merchant policy allow it?
8. Does Paari policy allow it?
9. Is transaction within spending limits?
10. Does risk check pass?
```

Then:

```text id="6u8x9y"
          ┌─────────────┐
          │   DECISION  │
          └──────┬──────┘
                 │
       ┌─────────┼─────────┐
       ▼         ▼         ▼
     ALLOW     REVIEW      DENY
```

For the MVP, **ALLOW** continues to payment.

---

# 3. The Gateway creates a payment authorization

This is where Paari becomes the security boundary.

For example:

```json id="wqg52l"
{
  "payment_authorization_id": "PA-001",
  "transaction_id": "TXN-001",
  "merchant_agent_id": "MA-001",
  "quote_id": "Q-001",
  "amount": 7000,
  "currency": "INR",
  "expires_at": "...",
  "status": "AUTHORIZED"
}
```

This says:

> Paari has authorized this exact transaction for this exact merchant and amount.

---

# 4. Gateway → Payment Service

Now the Gateway passes the approved transaction to your Payment Service:

```text id="iqdf23"
PAARI GOVERNANCE GATEWAY
          │
          │ authorized transaction
          ▼
   PAARI PAYMENT SERVICE
```

Keep this as a separate service/module even in your MVP.

Why?

Because later you can support:

```text id="czvfbk"
Razorpay
Stripe
PayU
Other PSPs
```

without changing the governance layer.

---

# 5. Payment Service → Razorpay

Now use the authorized data to create the Razorpay order/payment flow.

```text id="i1xqlx"
Paari Payment Service
        │
        │ amount = 7000
        │ currency = INR
        │ receipt = TXN-001
        ▼
     Razorpay
        │
        ▼
 Razorpay Order ID
```

Razorpay's documented Standard Checkout flow creates the order server-side and uses that order in the payment flow. The payment response is then verified server-side. 

### Important

Do **not** let the Merchant Agent decide the Razorpay amount independently.

Use:

```text
Paari-approved quote
        ↓
Paari-approved transaction amount
        ↓
Razorpay order
```

---

# 6. Return a payment action to the Buyer side

For your demo, the payment service produces a bounded payment session.

```json id="8n7s1f"
{
  "payment_session_id": "PS-001",
  "transaction_id": "TXN-001",
  "razorpay_order_id": "order_xxx",
  "amount": 7000,
  "currency": "INR",
  "expires_at": "...",
  "status": "PAYMENT_REQUIRED"
}
```

The Buyer Agent should receive **this controlled payment session**, not Razorpay secrets.

Razorpay's Standard Checkout itself still requires the supported checkout/payment interaction; an LLM cannot simply send `"PAY ₹7,000"` directly to Razorpay as a generic payment API. 

---

# 7. AI Buyer completes the Razorpay test payment

For your MVP:

```text id="y6u1dm"
Payment Session
      ↓
Razorpay Test Checkout
      ↓
Test payment
```

You can simulate successful and failed payments.

---

# 8. Razorpay → Paari

After the payment:

```text id="n3n4qz"
Razorpay
    │
    │ webhook / payment result
    ▼
Paari Payment Service
```

The Payment Service verifies:

```text id="3o8y2k"
✓ Razorpay order ID
✓ Payment ID
✓ Transaction ID
✓ Amount
✓ Currency
✓ Merchant
✓ Signature / webhook authenticity
```

Razorpay's documented integration requires server-side payment verification, including signature verification. 

---

# 9. Payment result → Governance Gateway

Now send the verified result back through Paari:

```text id="z0cgw4"
Razorpay
   ↓
Payment Service
   ↓
PAYMENT_VERIFIED
   ↓
Governance Gateway
```

Why send it back?

Because Paari should be the **central source of transaction authorization/state**, not the payment provider alone.

The Gateway can now change:

```text id="w0yz4j"
PAYMENT_PENDING
        ↓
PAYMENT_VERIFIED
```

---

# 10. Governance Gateway → Merchant Agent

Now tell the Merchant Agent:

```json id="un1f9b"
{
  "transaction_id": "TXN-001",
  "payment_status": "VERIFIED",
  "amount": 7000,
  "next_action": "FULFILL"
}
```

Merchant Agent can now safely continue.

```text id="zrbk8m"
PAYMENT_VERIFIED
       ↓
Merchant Agent
       ↓
Create/confirm order
       ↓
Dispatch
```

---

# 11. Your complete Phase 1 loop

This is exactly the loop you described:

```text id="6oq6qd"
                  PHASE 1

        ┌─────────────────────┐
        │   MERCHANT AGENT    │
        │                     │
        │ Deal / Quote        │
        │ Payment Request     │
        └──────────┬──────────┘
                   │
                   │ 1. Quote + Payment Request
                   ▼
        ┌─────────────────────┐
        │ PAARI GOVERNANCE    │
        │      GATEWAY        │
        │                     │
        │ Auth                │
        │ AuthZ               │
        │ Policy              │
        │ Risk                │
        │ Transaction         │
        └──────────┬──────────┘
                   │
                   │ 2. APPROVED
                   ▼
        ┌─────────────────────┐
        │ PAARI PAYMENT       │
        │      SERVICE        │
        └──────────┬──────────┘
                   │
                   │ 3. Create payment order
                   ▼
                RAZORPAY
                   │
                   │ 4. Test payment
                   ▼
        ┌─────────────────────┐
        │ PAARI PAYMENT       │
        │      SERVICE        │
        └──────────┬──────────┘
                   │
                   │ 5. Verify
                   ▼
        ┌─────────────────────┐
        │ PAARI GOVERNANCE    │
        │      GATEWAY        │
        └──────────┬──────────┘
                   │
                   │ 6. VERIFIED
                   ▼
        ┌─────────────────────┐
        │   MERCHANT AGENT    │
        └──────────┬──────────┘
                   │
                   ▼
             ORDER / FULFILL
```

# 12. What Phase 1 proves

At the end of Phase 1, you should be able to demonstrate:

```text
Merchant Agent
     ↓
"Here is a valid quote and payment request."
     ↓
Paari
     ↓
"Is this transaction allowed?"
     ↓
YES
     ↓
Razorpay Test Mode
     ↓
Payment
     ↓
Paari verifies
     ↓
Merchant Agent
     ↓
Order/fulfillment
```

And demonstrate a blocked case:

```text
Merchant Agent
     ↓
Quote ₹25,000
     ↓
Paari Policy
Maximum = ₹20,000
     ↓
DENY
     ↓
Razorpay NOT called
```

That's a very strong demo of your central proposition.

# 13. Phase 1 APIs

Keep the API surface small:

```text
POST /transactions
POST /transactions/{id}/authorize
POST /quotes
POST /quotes/{id}/payment-request

POST /payments/create
POST /payments/verify
POST /webhooks/razorpay

GET /transactions/{id}
GET /payments/{id}
GET /audit/{transaction_id}
```

Internally:

```text id="n4u5bt"
Merchant Agent
       ↓
Governance Gateway
       ↓
Transaction Service
       ↓
Payment Service
       ↓
Razorpay
```

# 14. Phase 2 then becomes easy

Once Phase 1 works, **don't redesign the payment system**.

Add:

```text id="7oh0k4"
AI Buyer Agent
       │
       │ A2A
       ▼
PAARI AGENT GATEWAY
       │
       ▼
Merchant Agent
       │
       ▼
[Existing Phase 1 Payment Core]
       │
       ▼
Razorpay
```

So A2A becomes the **communication layer above your already-tested transaction/payment engine**.

### The one architecture decision I strongly recommend

Use:

```text
Merchant Agent
      ↓
Paari Governance Gateway
      ↓
Paari Payment Service
      ↓
Razorpay
```

rather than:

```text
Merchant Agent
      ↓
Razorpay
```

That keeps **governance, authorization, transaction state, and audit inside Paari**, while Razorpay remains the actual payment processor. This aligns with the payment architecture in your attached design, where Paari acts as the authorized orchestration/control layer rather than becoming the payment processor itself.

--------------------------------------------------------------------

Yes. **Phase 2 should wire the AI Buyer Agent into the already-tested Phase 1 transaction/payment core**, then prove one complete agentic purchase.

## Phase 2 objective

```text id="y4z9h2"
AI BUYER AGENT
      │
      │ A2A
      ▼
PAARI GOVERNANCE GATEWAY
      │
      ├── Authenticate buyer agent
      ├── Authorize capabilities
      ├── Apply Paari policies
      └── Route request
      │
      ▼
MERCHANT AGENT
      │
      ├── Understand store
      ├── Check inventory
      ├── Negotiate
      └── Create quote
      │
      ▼
PAARI GOVERNANCE GATEWAY
      │
      ├── Validate quote
      ├── Validate transaction
      └── Authorize payment
      │
      ▼
PAYMENT SESSION
      │
      ▼
AI BUYER AGENT
      │
      │ executes authorized payment
      ▼
RAZORPAY TEST MODE
      │
      ▼
PAYMENT RESULT / WEBHOOK
      │
      ▼
PAARI
      │
      ├── Verify payment
      └── Update transaction
      │
      ▼
MERCHANT AGENT
      │
      ▼
SHOPIFY ORDER / FULFILLMENT
```

# Step 1 — Connect AI Buyer Agent to Paari

Start with **agent registration**.

```text
Buyer Agent
  ↓
Paari
  ↓
Register agent
  ↓
BA-001
```

Give it:

```text
agent_id
user_id
capabilities
credential
status
```

For example:

```json
{
  "agent_id": "BA-001",
  "capabilities": [
    "catalog.read",
    "inventory.read",
    "quote.request",
    "quote.accept",
    "payment.execute"
  ]
}
```

---

# Step 2 — Build A2A connection

Now connect:

```text
AI Buyer Agent
       ↕
   A2A Protocol
       ↕
Paari Gateway
```

Keep A2A focused on **communication and message exchange**.

Paari still controls:

```text
authentication
authorization
governance
risk
transaction
payment
```

---

# Step 3 — Buyer discovers Merchant Agent

The Buyer Agent asks:

```text
"Find a merchant that sells snowboards."
```

Paari returns an active Merchant Agent:

```json
{
  "merchant_agent_id": "MA-001",
  "merchant_id": "MER-001",
  "store_id": "STORE-001",
  "capabilities": [
    "catalog.search",
    "inventory.read",
    "quote.request",
    "deal.negotiate",
    "checkout.request"
  ]
}
```

Now the Buyer Agent knows who it can communicate with.

---

# Step 4 — Buyer Agent requests products

```text
BA-001
   ↓ A2A
Paari
   ↓
MA-001
   ↓
Shopify
```

Buyer says:

> "Find me snowboards below ₹8,000."

Merchant Agent calls:

```text
search_products()
```

and:

```text
check_inventory()
```

Then responds with valid products.

---

# Step 5 — Buyer requests a purchase

Buyer Agent sends:

```json
{
  "action": "BUY_REQUEST",
  "product_id": "P001",
  "quantity": 1
}
```

Paari verifies:

```text
✓ Buyer authenticated
✓ Buyer authorized
✓ Merchant Agent active
✓ Capability allowed
✓ Transaction allowed
```

Then forwards to Merchant Agent.

---

# Step 6 — Merchant Agent creates the deal

Merchant Agent evaluates:

```text
Product
Price
Inventory
Shipping
Discount
Merchant policies
Paari policies
```

Then creates:

```text
QUOTE
```

Example:

```json
{
  "quote_id": "Q-001",
  "transaction_id": "TXN-001",
  "amount": 7000,
  "currency": "INR",
  "expires_at": "..."
}
```

---

# Step 7 — Buyer accepts quote

Buyer Agent sends:

```text
ACCEPT_QUOTE Q-001
```

Paari validates again:

```text
Quote valid?
Not expired?
Amount unchanged?
Merchant still active?
Buyer still authorized?
Policy still valid?
```

Then:

```text
TRANSACTION = PAYMENT_PENDING
```

---

# Step 8 — Paari creates payment session

Now the important part:

```text
Merchant Agent
      ↓
Paari Transaction Service
      ↓
Payment Session
```

Example:

```json
{
  "payment_session_id": "PS-001",
  "transaction_id": "TXN-001",
  "amount": 7000,
  "currency": "INR",
  "expires_at": "...",
  "status": "AUTHORIZED"
}
```

The Buyer Agent receives **only this transaction-specific payment authorization**, not Razorpay secrets.

---

# Step 9 — AI Buyer makes the payment

Now the Buyer Agent uses the authorized payment session:

```text
AI Buyer Agent
      ↓
PS-001
      ↓
Razorpay Test Checkout / supported payment flow
      ↓
Test payment
```

The important distinction is:

> **AI Buyer Agent is allowed to execute the specific authorized payment; it does not get generic access to the payment gateway.**

Razorpay's Standard Checkout still requires the supported checkout/payment interaction and subsequent server-side verification. 

---

# Step 10 — Razorpay sends payment result

```text
Razorpay
   ↓
Webhook / Payment result
   ↓
Paari Payment Service
```

Paari checks:

```text
transaction
quote
amount
Razorpay order
payment status
signature/webhook
merchant
```

Then:

```text
PAYMENT_VERIFIED
```

Razorpay's documented flow requires server-side verification of the payment response/signature. 

---

# Step 11 — Notify Merchant Agent

Paari sends:

```json
{
  "transaction_id": "TXN-001",
  "payment_status": "VERIFIED",
  "next_action": "FULFILL"
}
```

Merchant Agent now knows it can continue.

---

# Step 12 — Create Shopify order

```text
PAYMENT_VERIFIED
       ↓
Merchant Agent
       ↓
Shopify
       ↓
Order Created
       ↓
Fulfillment
```

The order must not be created based only on the Buyer Agent saying "paid."

---

# Step 13 — Add complete A2A responses

The Buyer Agent should receive:

```text
DISCOVERY
    ↓
PRODUCT_RESULT
    ↓
QUOTE
    ↓
PAYMENT_REQUIRED
    ↓
PAYMENT_VERIFIED
    ↓
ORDER_CONFIRMED
```

So the Buyer Agent can maintain a clear transaction state.

---

# Step 14 — Add failure handling

Test these:

### Unauthorized agent

```text
Buyer → Paari
      ↓
AUTH FAILED
      ↓
DENY
```

### Policy violation

```text
Buyer
 ↓
Buy ₹25,000
 ↓
Merchant max = ₹20,000
 ↓
DENY
 ↓
No payment
```

### Payment failure

```text
Quote
 ↓
Razorpay
 ↓
FAILED
 ↓
Paari
 ↓
PAYMENT_FAILED
 ↓
No order
```

### Duplicate payment request

```text
PAY TXN-001
PAY TXN-001 again
       ↓
Idempotency check
       ↓
Do not create duplicate transaction/payment
```

### Payment succeeds but Shopify fails

```text
Payment VERIFIED
      ↓
Shopify error
      ↓
Transaction = FULFILLMENT_PENDING
      ↓
Retry/reconciliation
```

This is essential for reliable agentic transactions.

---

# Step 15 — Full Phase 2 flow

```text id="k8mwf0"
                    AI BUYER AGENT
                           │
                           │ A2A
                           ▼
                  PAARI A2A GATEWAY
                           │
                 Authentication
                 Authorization
                 Capability
                 Governance
                 Risk
                           │
                           ▼
                    MERCHANT AGENT
                           │
                           ▼
                       SHOPIFY
                           │
                    Products/Stock
                           │
                           ▼
                      NEGOTIATION
                           │
                           ▼
                         QUOTE
                           │
                           ▼
                   QUOTE ACCEPTED
                           │
                           ▼
                 PAARI TRANSACTION
                           │
                           ▼
                  PAYMENT SESSION
                           │
                           ▼
                    AI BUYER AGENT
                           │
                           ▼
                       RAZORPAY
                           │
                           ▼
                  PAYMENT VERIFIED
                           │
                           ▼
                    MERCHANT AGENT
                           │
                           ▼
                    SHOPIFY ORDER
                           │
                           ▼
                       FULFILLMENT
                           │
                           ▼
                         AUDIT
```

## Phase 2 implementation order

```text
1. Register Buyer Agent
        ↓
2. Implement A2A transport/message layer
        ↓
3. Buyer → Paari authentication
        ↓
4. Buyer → Merchant Agent discovery
        ↓
5. Product discovery
        ↓
6. Buy request
        ↓
7. Merchant Agent quote
        ↓
8. Quote acceptance
        ↓
9. Payment session
        ↓
10. Buyer executes authorized Razorpay payment
        ↓
11. Razorpay verification
        ↓
12. Merchant Agent notified
        ↓
13. Shopify order
        ↓
14. Order status back to Buyer Agent
        ↓
15. Failure/retry/idempotency testing
```

### The key Phase-2 principle

```text
A2A = communication
Paari = trust + governance + authorization
Merchant Agent = merchant-side intelligence/execution
Razorpay = payment execution
Shopify = commerce/order system
```

So you are **not rebuilding Phase 1**. You are putting the AI Buyer Agent and A2A communication around the already-tested **Paari → Razorpay → verification → Merchant Agent** transaction core.
-----------------------------------------------
Yes. This is the **correct end-to-end transaction model** for Paari.

The key idea is:

> **Buyer Agent + Merchant Agent make the commercial deal. Merchant Agent then submits the finalized transaction to Paari. Paari independently authenticates/authorizes the buyer and governs whether that agreed deal can become a payment.**

Your current codebase already supports this overall structure: the Merchant Agent creates/accepts the quote, Governance evaluates the transaction, then the Payment Service creates the payment session/capability and routes to Razorpay. 

# 1. Final overall architecture

```text
                         USER
                           │
                           ▼
                  ┌────────────────┐
                  │ AI BUYER AGENT │
                  └───────┬────────┘
                          │
                          │ A2A / communication
                          ▼
                  ┌─────────────────┐
                  │ MERCHANT AGENT  │
                  └────────┬────────┘
                           │
                    negotiate / quote
                           │
                           ▼
                    FINAL QUOTATION
                           │
                   buyer accepts
                           │
                           ▼
                  FINAL DEAL CONFIRMED
                           │
                           │
                  Merchant Agent sends
                  payment request + quote
                  + buyer identity
                           │
                           ▼
             ┌──────────────────────────┐
             │       PAARI GATEWAY      │
             │                          │
             │ Request validation       │
             │ Authentication           │
             │ Governance               │
             │ Authorization            │
             │ Policy                   │
             │ Risk                     │
             │ Transaction              │
             └────────────┬─────────────┘
                          │
                    ALLOW / REVIEW / DENY
                          │
                          ▼
                  PAYMENT AUTHORIZATION
                          │
                          ▼
                  PAYMENT SESSION
                  + ONE-TIME CAPABILITY
                          │
                          ▼
                       RAZORPAY
                          │
                          ▼
                      PAYMENT
                          │
                          ▼
                  RAZORPAY WEBHOOK
                          │
                          ▼
                PAARI PAYMENT VERIFICATION
                          │
                          ▼
                   TRANSACTION UPDATED
                          │
                          ▼
                    AUDIT + LOGGING
                          │
                          ▼
                  MERCHANT AGENT
                          │
                          ▼
                       STORE
```

---

# 2. Step 1 — Buyer Agent communicates with Merchant Agent

The first phase is **commerce**, not payment.

```text
Buyer Agent
     ↕
Merchant Agent
```

They can perform:

```text
DISCOVER
REQUEST_QUOTE
NEGOTIATE
COUNTER_OFFER
ACCEPT_QUOTE
```

Your existing A2A model already defines these actions. 

Example:

```text
Buyer:
"I need Burton snowboard under ₹5,000."

Merchant:
"₹4,900."

Buyer:
"Can you do ₹4,700?"

Merchant:
"₹4,799 final."

Buyer:
"Accepted."
```

---

# 3. Step 2 — Final quotation becomes the agreement

Merchant Agent generates the final quote:

```json
{
  "quote_id": "Q-001",
  "buyer_agent_id": "BA-001",
  "merchant_agent_id": "MA-001",

  "items": [
    {
      "sku": "NIKE-001",
      "quantity": 1,
      "unit_price": 4599
    }
  ],

  "shipping": 100,
  "tax": 100,
  "total": 4799,

  "currency": "INR",

  "status": "ACCEPTED",
  "expires_at": "..."
}
```

This is important:

```text
LLM conversation
       ↓
FINAL QUOTE
       ↓
AUTHORITATIVE COMMERCIAL DATA
```

Paari should govern based on the **structured quote**, not on a natural-language conversation.

Your existing schema follows this model, including `quote_id`, transaction relationship, total, expiry, and policy version. 

---

# 4. Step 3 — Merchant Agent sends payment request to Paari

This is the point where **Paari takes control**.

Merchant Agent sends:

```json
{
  "request_type": "PAYMENT_REQUEST",

  "transaction_id": "TXN-001",
  "quote_id": "Q-001",

  "buyer_agent_id": "BA-001",
  "merchant_agent_id": "MA-001",

  "amount": 4799,
  "currency": "INR"
}
```

Conceptually:

```text
Merchant Agent says:

"The deal is finalized.
Here is the buyer identity.
Here is the accepted quote.
Please authorize payment."
```

---

# 5. Step 4 — Paari creates/loads the transaction context

Paari now creates or loads:

```text
TXN-001
```

Then loads:

```text
Buyer Agent
Merchant
Quote
User Policy
Merchant Policy
Paari Policy
Payment Session
Payment Capability
```

Your current `GovernanceContext.load()` is already designed to load essentially this full context. 

So the governance context becomes:

```text
                    GOVERNANCE CONTEXT

Buyer Agent ─────────────┐
Merchant ────────────────┤
Quote ───────────────────┤
Transaction ─────────────┤
User Policy ─────────────┤
Merchant Policy ─────────┤
Paari Policy ────────────┤
Payment Session ─────────┤
Payment Capability ──────┘
```

---

# 6. Step 5 — Paari authenticates the buyer identity

Now Paari answers:

> **Who is this AI buyer?**

The identity should not simply be trusted because the Merchant Agent sent:

```text
buyer_agent_id = BA-001
```

Paari verifies the requester's credentials/identity.

Your existing system uses RS256 JWTs with JWKS, expiry, issuer and revocation checks. 

So:

```text
Payment Request
      ↓
JWT / credential verification
      ↓
BA-001
      ↓
ACTIVE?
      ↓
AUTHENTICATED
```

---

# 7. Step 6 — Governance checks the transaction

Now the key stage.

Your existing active governance pipeline has eight checks:

```text
1. Agent identity
2. Agent authorization
3. Merchant authorization
4. Quote validation
5. Amount policy
6. User spending limit
7. Autonomous payment
8. Risk
```

The report explicitly defines these checks. 

So:

```text
Payment Request
      ↓
┌───────────────────────────────┐
│     PAARI GOVERNANCE          │
├───────────────────────────────┤
│ Buyer identity       ✓        │
│ Buyer authorization  ✓        │
│ Merchant             ✓        │
│ Quote                ✓        │
│ Amount               ✓        │
│ User limit           ✓        │
│ Autonomous payment  ✓        │
│ Risk                 ✓        │
└───────────────┬───────────────┘
                │
         ALLOW / REVIEW / DENY
```

The decision model is explicitly `DENY > REVIEW > ALLOW`. 

---

# 8. Step 7 — If ALLOW, Paari authorizes a bounded payment

This is where you turn governance into **payment authority**.

```text
ALLOW
  ↓
Payment Session
  ↓
One-time payment capability
```

Example:

```json
{
  "session_id": "PS-001",
  "transaction_id": "TXN-001",

  "authorized_amount": 4799,

  "status": "ACTIVE",
  "expires_at": "..."
}
```

And:

```json
{
  "capability_id": "CAP-001",
  "transaction_id": "TXN-001",
  "action": "payment.execute",
  "max_amount": 4799,
  "usage": "ONE_TIME",
  "used": false
}
```

Your existing payment service already creates a 10-minute session and a one-time `payment.execute` capability after governance approval. 

This is an important concept:

> **Paari does not give the AI buyer unrestricted payment access. It gives it authority for one specific governed transaction.**

---

# 9. Step 8 — Paari creates the Razorpay order

Now the Payment Service uses the authorized transaction.

```text
Paari authorized amount = ₹4,799
             ↓
Razorpay Order
```

Store the mapping:

```text
PAARI TXN-001
      ↕
Razorpay order_ABC
```

Your current implementation already stores the Razorpay order ID on the transaction. 

---

# 10. Step 9 — AI Buyer makes the payment

The Buyer Agent receives the controlled payment information:

```text
transaction_id
payment_session_id
razorpay_order_id
authorized amount
expiry
```

Then the payment is completed through Razorpay.

Conceptually:

```text
AI Buyer Agent
       ↓
Paari payment session
       ↓
Razorpay order
       ↓
Payment
```

The AI buyer should **not receive Paari's or Razorpay's secret credentials**.

---

# 11. Step 10 — Razorpay reports payment result to Paari

After the payment:

```text
Razorpay
    ↓
Webhook
    ↓
Paari
```

Paari verifies the event, deduplicates it, finds the associated transaction, and updates state.

Your existing webhook flow does this for captured payments and marks the transaction as `PAYMENT_VERIFIED`, completes the session, and consumes the payment capability. 

---

# 12. Step 11 — Paari reconciles everything

Now Paari checks:

```text
               PAARI
                 │
       ┌─────────┼─────────┐
       ▼         ▼         ▼
     Quote    Transaction  Razorpay
       │         │         │
       └─────────┼─────────┘
                 ▼
             CONSISTENT?
```

For example:

```text
Quote:         ₹4,799
Transaction:   ₹4,799
Razorpay:      ₹4,799
```

→ PASS.

But:

```text
Quote:         ₹4,799
Transaction:   ₹4,799
Razorpay:      ₹7,999
```

→ REJECT.

This is an especially important security property of your design.

---

# 13. Step 12 — Audit everything

Every important decision is logged.

```text
TXN-001

Buyer authenticated
Buyer authorization passed
Merchant verified
Quote validated
Amount validated
User spending limit passed
Autonomous payment allowed
Risk passed
Governance approved
Payment session created
Capability issued
Razorpay order created
Payment received
Payment verified
Capability consumed
```

Your implementation already makes audit synchronous with enforcement, including fail-closed behavior if the audit write fails. 

---

# 14. Step 13 — Notify Merchant Agent

After:

```text
PAYMENT_VERIFIED
```

Paari tells the Merchant Agent:

```json
{
  "transaction_id": "TXN-001",
  "status": "PAYMENT_VERIFIED"
}
```

Then Merchant Agent can proceed to fulfillment.

Your current A2A flow explicitly follows `PAYMENT_RESULT` with `FULFILL_ORDER`, after payment verification. 

---

# 15. Complete data flow

This is the version I would use as the **final architecture diagram**:

```text
┌──────────────┐
│    USER      │
└──────┬───────┘
       │
       ▼
┌──────────────────┐
│ AI BUYER AGENT   │
└────────┬─────────┘
         │
         │ DISCOVER / NEGOTIATE
         │ QUOTE / ACCEPT
         ▼
┌──────────────────┐
│ MERCHANT AGENT   │
└────────┬─────────┘
         │
         ▼
   FINAL QUOTE
   + BUYER IDENTITY
         │
         │ PAYMENT REQUEST
         ▼
╔════════════════════════════════════╗
║          PAARI GATEWAY             ║
║                                    ║
║  Authentication                    ║
║        ↓                           ║
║  Agent Authorization               ║
║        ↓                           ║
║  Merchant Authorization            ║
║        ↓                           ║
║  Quote Validation                  ║
║        ↓                           ║
║  Amount Validation                 ║
║        ↓                           ║
║  User Spending Policy              ║
║        ↓                           ║
║  Autonomous Payment Policy         ║
║        ↓                           ║
║  Risk                             ║
║        ↓                           ║
║  ALLOW / REVIEW / DENY             ║
╚══════════════════╤═════════════════╝
                   │
                 ALLOW
                   │
                   ▼
          PAYMENT SESSION
                   +
          ONE-TIME CAPABILITY
                   │
                   ▼
             RAZORPAY
                   │
                   ▼
             AI BUYER PAYS
                   │
                   ▼
             RAZORPAY
                   │
                WEBHOOK
                   ▼
        PAARI PAYMENT VERIFICATION
                   │
                   ▼
             RECONCILIATION
                   │
                   ▼
              AUDIT EVENT
                   │
                   ▼
          PAYMENT_VERIFIED
                   │
                   ▼
            MERCHANT AGENT
                   │
                   ▼
                SHOPIFY
```

---

# 16. The responsibility of each component

| Component                      | Responsibility                                                                   |
| ------------------------------ | -------------------------------------------------------------------------------- |
| **AI Buyer Agent**             | User intent, product selection, negotiation                                      |
| **Merchant Agent**             | Merchant representation, product info, negotiation, final quote, payment request |
| **Paari Gateway**              | Entry/control point for payment requests                                         |
| **Governance Engine**          | Decide whether transaction is permitted                                          |
| **Policy Engine**              | Enforce Paari/user/merchant rules                                                |
| **Risk Engine**                | Detect suspicious/high-risk transactions                                         |
| **Payment Session/Capability** | Bound the payment authority                                                      |
| **Razorpay**                   | Execute actual payment                                                           |
| **Paari Verification**         | Determine whether payment is genuinely valid                                     |
| **Audit**                      | Record what happened and why                                                     |
| **Merchant Agent/Shopify**     | Fulfill after verified payment                                                   |

---

# 17. One subtle but important architectural point

The **Merchant Agent should not be the ultimate authority for the buyer identity**.

It can **send the buyer identity**, but Paari should verify it independently.

So:

```text
Merchant Agent says:

Buyer = BA-001
```

does **not** mean:

```text
Paari trusts BA-001
```

Instead:

```text
Merchant Agent
      ↓
"buyer_agent_id = BA-001"
      ↓
PAARI
      ↓
Authenticate BA-001
      ↓
Authorize BA-001
      ↓
Govern transaction
```

That makes Paari the neutral trust/governance layer between the two agents.

---

# 18. This is what makes a merchant "AI-transactable"

The important distinction is:

```text
Traditional merchant
      ↓
Website
      ↓
Human checkout
```

versus:

```text
AI Buyer
      ↕
Merchant Agent
      ↓
Final Deal
      ↓
Paari Governance
      ↓
Bounded Agentic Payment
      ↓
Razorpay
      ↓
Verified Fulfillment
```

So your product isn't simply:

> **"An AI agent that can make payments."**

It is:

> **"A governed transaction gateway that allows authorized AI buyer agents to turn an agent-to-agent commercial agreement into a bounded, auditable payment with an AI-transactable merchant."**

That is the architecture I would now freeze as your **Paari Phase 1 core**. Your codebase is already remarkably close to this model; the remaining work is primarily validating that the existing components execute this exact flow and tightening any boundaries where the implementation differs from the intended architecture.
-------------------------------------------------
Yes. That is the right strategy: **your friend completes Phase 2 A2A integration, and once the entire architecture is connected, you showcase a small set of end-to-end test cases that prove Paari's core value.**

The demo should revolve around your four words:

> **Every money action is explainable, bounded, and gated.**

## Final showcase architecture

```text
AI BUYER AGENT
      │
      │ A2A
      ▼
MERCHANT AGENT
      │
      │ Final deal + accepted quote
      │ + payment request
      ▼
PAARI GATEWAY
      │
      ├── Identity
      ├── Authorization
      ├── Paari policies
      ├── User policies
      ├── Merchant policies
      ├── Quote validation
      ├── Amount bound
      ├── Session
      ├── Capability
      └── Risk
      │
      ▼
ALLOW / REVIEW / DENY
      │
      ▼
RAZORPAY
      │
      ▼
Payment
      │
      ▼
Verification
      │
      ▼
Merchant Agent
      │
      ▼
Store / Order
```

Your existing implementation already has the governance pipeline, bounded session/capability model, payment verification, and audit trail that support this demonstration.  

# The 4 showcase cases

You don't need to demonstrate every possible rule. Pick four cases that tell the complete story.

### 1. Successful agentic payment — **ALLOW**

```text
Buyer Agent
   ↓
Merchant Agent
   ↓
Deal agreed
   ↓
Quote = ₹4,799
   ↓
Payment request
   ↓
Paari Governance
   ↓
ALL CHECKS PASS
   ↓
ALLOW
   ↓
Payment session issued
   ↓
Razorpay
   ↓
Payment succeeds
   ↓
Paari verifies
   ↓
Merchant fulfills
```

Dashboard:

```text
TRANSACTION: TXN-001
Decision: ALLOW

✓ Buyer authenticated
✓ Buyer authorized
✓ Merchant authorized
✓ Quote accepted
✓ Amount = ₹4,799
✓ User limit = ₹5,000
✓ Autonomous payment = allowed
✓ Session valid
✓ Capability valid
✓ Risk = LOW

Payment: VERIFIED
Fulfillment: AUTHORIZED
```

**This proves "gated + bounded + explainable."**

---

### 2. Amount manipulation — **DENY**

This is probably your strongest security demo.

Suppose:

```text
Final quote = ₹4,799
```

but the payment request attempts:

```text
₹7,999
```

Flow:

```text
Merchant Agent
      ↓
Quote = ₹4,799
      ↓
Payment request = ₹7,999
      ↓
Paari
      ↓
AMOUNT MISMATCH
      ↓
DENY
      ↓
NO PAYMENT SESSION
NO CAPABILITY
NO RAZORPAY CALL
```

Dashboard:

```text
PAYMENT BLOCKED

Quote amount: ₹4,799
Requested amount: ₹7,999

Reason:
Transaction amount does not match
the agreed quotation.

Result:
DENIED
```

Your recent verification specifically confirms this invariant: the Razorpay adapter is not called when the authorized/session amount does not match the transaction. That is an excellent demo boundary.

---

### 3. User spending-policy violation — **REVIEW/DENY**

Example:

```text
User autonomous limit = ₹5,000
Transaction = ₹7,000
```

Depending on your configured policy:

```text
₹7,000
   ↓
Policy violation
   ↓
REVIEW or DENY
```

For demonstration, **REVIEW** can be more visually interesting:

```text
Transaction
   ↓
Governance
   ↓
REVIEW_REQUIRED
   ↓
Human dashboard
   ↓
Approve / Deny
```

Your existing implementation has a review queue and re-checks the transaction through the gateway if an operator approves it. 

This demonstrates that autonomy is **bounded, not absolute**.

---

### 4. Payment failure — graceful recovery

This satisfies your:

> **"one failure handled gracefully."**

Use:

```text
Governance = ALLOW
      ↓
Razorpay
      ↓
PAYMENT_FAILED
      ↓
Paari state = PAYMENT_FAILED
      ↓
NO fulfillment
      ↓
Buyer gets clear explanation
```

Dashboard:

```text
PAYMENT FAILED

Transaction: TXN-004
Amount: ₹4,799
Governance: APPROVED

Payment processor:
FAILED

Fulfillment:
BLOCKED

Next action:
Payment may be retried according to policy.
```

The important thing is that **payment failure does not cause an order to be fulfilled**.

---

# What to show on the dashboard

The dashboard should not just show:

```text
Payment Successful
```

Instead show three sections.

### Decision

```text
GOVERNANCE DECISION

ALLOW
```

### Why

```text
✓ Agent verified
✓ Agent authorized
✓ Merchant verified
✓ Quote valid
✓ Amount within bound
✓ User policy satisfied
✓ Autonomous payment allowed
✓ Session valid
✓ Capability valid
✓ Risk acceptable
```

### What happened

```text
13:10:02 Deal confirmed
13:10:03 Payment request received
13:10:03 Governance approved
13:10:03 Payment session created
13:10:04 Razorpay order created
13:10:21 Payment received
13:10:22 Payment verified
13:10:22 Fulfillment authorized
```

Your current audit implementation already records each enforcement decision synchronously before returning the response. 

# The one slide/demo narrative

I would present the whole project through this story:

```text
1. AI Buyer and Merchant Agent negotiate.
                 ↓
2. They agree on a quotation.
                 ↓
3. Merchant Agent asks Paari to authorize payment.
                 ↓
4. Paari independently verifies identity,
   authorization, policies and transaction bounds.
                 ↓
5. Paari either ALLOWS, REVIEWS or DENIES.
                 ↓
6. Only an authorized transaction gets a payment capability.
                 ↓
7. Razorpay executes the payment.
                 ↓
8. Paari verifies the payment result.
                 ↓
9. Merchant fulfills only after verification.
                 ↓
10. Everything is auditable and explainable.
```

# The message you should prove

The strongest demo statement is:

> **The AI agents can negotiate freely, but they cannot freely move money.**

That's the essence of Paari.

The **deal is agentic**.

The **payment is governed**.

The **money action is bounded**.

The **decision is explainable**.

The **result is auditable**.

Your existing codebase already has most of the machinery for exactly this: A2A actions, Merchant Agent, Governance Engine, Payment Service, Razorpay integration, verification, review handling, and audit. 

So once your friend finishes Phase 2, I would **avoid adding major new features before the demo**. Instead, run these four canonical scenarios end-to-end and capture the **agent conversation → final quote → Paari decision → payment → verification → audit timeline** for each. That will make the architecture immediately understandable to judges, investors, or companies.

Absolutely. You should show **both**:

1. **Overall Paari architecture + end-to-end data flow**
2. **Four proof test cases** demonstrating that the flow is governed.

Your uploaded technical report already supports this architecture: Buyer Agent ↔ Merchant Agent through A2A, quote acceptance, Paari Governance, payment session/capability, Razorpay payment, verification, and fulfillment. 

# 1. Overall architecture to showcase

I would use this as your **main architecture diagram**:

```text
                              ┌──────────────┐
                              │     USER     │
                              └──────┬───────┘
                                     │
                                     ▼
                           ┌──────────────────┐
                           │  AI BUYER AGENT  │
                           │                  │
                           │ Intent           │
                           │ Product choice   │
                           │ Negotiation      │
                           └────────┬─────────┘
                                    │
                                    │ A2A
                                    │
                                    ▼
                           ┌──────────────────┐
                           │ MERCHANT AGENT   │
                           │                  │
                           │ Catalog          │
                           │ Inventory        │
                           │ Pricing          │
                           │ Negotiation      │
                           │ Quote            │
                           └────────┬─────────┘
                                    │
                           FINAL DEAL + QUOTE
                                    │
                           PAYMENT REQUEST
                           + BUYER IDENTITY
                                    │
                                    ▼
              ╔════════════════════════════════════════════╗
              ║              PAARI GATEWAY                 ║
              ║                                            ║
              ║  Authentication                            ║
              ║       ↓                                    ║
              ║  Agent Authorization                       ║
              ║       ↓                                    ║
              ║  Merchant Authorization                    ║
              ║       ↓                                    ║
              ║  Quote / Agreement Validation               ║
              ║       ↓                                    ║
              ║  Amount Validation                         ║
              ║       ↓                                    ║
              ║  User Spending Policy                      ║
              ║       ↓                                    ║
              ║  Merchant / Paari Policy                   ║
              ║       ↓                                    ║
              ║  Autonomous Payment Policy                 ║
              ║       ↓                                    ║
              ║  Risk Engine                               ║
              ║       ↓                                    ║
              ║  Session + Capability                      ║
              ║       ↓                                    ║
              ║   ALLOW / REVIEW / DENY                    ║
              ╚════════════════════╤═══════════════════════╝
                                   │
                         ALLOW + BOUNDED AUTH
                                   │
                                   ▼
                          ┌─────────────────┐
                          │    RAZORPAY     │
                          │                 │
                          │ Order           │
                          │ Checkout        │
                          │ Payment         │
                          └────────┬────────┘
                                   │
                              PAYMENT EVENT
                                   │
                                   ▼
                          ┌─────────────────┐
                          │ PAARI VERIFY    │
                          │                 │
                          │ Signature       │
                          │ Order match     │
                          │ Amount match    │
                          │ Payment state  │
                          └────────┬────────┘
                                   │
                            PAYMENT VERIFIED
                                   │
                 ┌─────────────────┴─────────────────┐
                 │                                   │
                 ▼                                   ▼
          ┌───────────────┐                  ┌──────────────┐
          │ AUDIT / LOG   │                  │ MERCHANT     │
          │               │                  │ AGENT        │
          │ All decisions │                  │              │
          │ All events   │                  │ Fulfillment  │
          └───────────────┘                  └──────┬───────┘
                                                   │
                                                   ▼
                                               SHOPIFY
```

Your current implementation has the corresponding Gateway, governance, payment, webhook, and audit endpoints/modules.  

# 2. Show the data flow separately

Don't rely only on the architecture boxes. Show **what data actually moves**.

### Step 1 — Buyer intent

```json
{
  "buyer_agent_id": "BA-001",
  "intent": "buy Nike running shoes",
  "constraints": {
    "max_price": 5000
  }
}
```

```text
AI BUYER
   ↓
Merchant Agent
```

### Step 2 — Negotiation

```text
Buyer Agent
    ↕
Merchant Agent
    │
    ├── product
    ├── price
    ├── discount
    ├── shipping
    └── terms
```

### Step 3 — Final quote

```json
{
  "quote_id": "Q-001",
  "transaction_id": "TXN-001",
  "buyer_agent_id": "BA-001",
  "merchant_agent_id": "MA-001",
  "total": 4799,
  "currency": "INR",
  "status": "ACCEPTED",
  "expires_at": "..."
}
```

The current system models accepted quotes and their relationship to transactions. 

### Step 4 — Payment request to Paari

```json
{
  "transaction_id": "TXN-001",
  "quote_id": "Q-001",
  "buyer_agent_id": "BA-001",
  "merchant_agent_id": "MA-001",
  "amount": 4799,
  "currency": "INR",
  "action": "PAYMENT_REQUEST"
}
```

### Step 5 — Paari governance context

Paari loads:

```text
Transaction
Buyer Agent
Merchant
Quote
User Policy
Merchant Policy
Paari Policy
Payment Session
Payment Capability
```

Your existing `GovernanceContext.load()` is designed around this context. 

### Step 6 — Governance decision

```json
{
  "transaction_id": "TXN-001",
  "decision": "ALLOW",
  "checks": {
    "agent_identity": "PASS",
    "agent_authorization": "PASS",
    "merchant_authorization": "PASS",
    "quote_validation": "PASS",
    "amount_policy": "PASS",
    "user_spending_limit": "PASS",
    "autonomous_payment": "PASS",
    "risk": "PASS"
  }
}
```

The current engine aggregates decisions using `DENY > REVIEW > ALLOW`. 

### Step 7 — Bounded payment authority

```json
{
  "session_id": "PS-001",
  "transaction_id": "TXN-001",
  "authorized_amount": 4799,
  "expires_at": "...",
  "status": "ACTIVE"
}
```

and:

```json
{
  "capability_id": "CAP-001",
  "action": "payment.execute",
  "transaction_id": "TXN-001",
  "max_amount": 4799,
  "usage": "ONE_TIME"
}
```

Your current payment service creates these after governance approval. 

### Step 8 — Razorpay

```text
Paari authorized amount
        ↓
Razorpay Order
        ↓
Payment
```

### Step 9 — Verification

```text
Razorpay event
      ↓
Paari webhook
      ↓
Verify
      ↓
Match transaction
      ↓
Match order
      ↓
Match amount
      ↓
Payment verified
```

The current webhook implementation also deduplicates events and updates transaction/session/capability state. 

### Step 10 — Fulfillment + audit

```text
PAYMENT_VERIFIED
       │
       ├──────────────► AUDIT
       │
       ▼
MERCHANT AGENT
       ↓
SHOPIFY
       ↓
ORDER
```

---

# 3. Show the control flow beside the data flow

This is even more useful in the presentation.

```text
DATA FLOW

Buyer request
     ↓
Negotiation
     ↓
Quote
     ↓
Payment request
     ↓
Governance context
     ↓
Payment session
     ↓
Razorpay order
     ↓
Payment event
     ↓
Verified payment
     ↓
Order
```

And:

```text
CONTROL FLOW

                    PAARI
                      │
       ┌──────────────┼──────────────┐
       ▼              ▼              ▼
 Authentication    Authorization    Policy
       │              │              │
       └──────────────┼──────────────┘
                      ▼
                    Risk
                      │
                      ▼
                   Decision
                 /    |     \
             ALLOW  REVIEW  DENY
                │      │       │
                ▼      ▼       ▼
             Payment  Human   STOP
```

This makes it immediately obvious that **the commercial conversation is separated from financial authorization**.

# 4. Then show the four proof scenarios

After the architecture slide, show:

### Scenario A — Normal transaction

```text
QUOTE ₹4,799
     ↓
GOVERNANCE PASS
     ↓
ALLOW
     ↓
RAZORPAY
     ↓
PAYMENT VERIFIED
     ↓
FULFILL
```

### Scenario B — Amount manipulation

```text
QUOTE = ₹4,799
REQUEST = ₹7,999
       ↓
AMOUNT MISMATCH
       ↓
DENY
       ↓
NO PAYMENT
```

### Scenario C — User policy violation

```text
USER LIMIT = ₹5,000
TRANSACTION = ₹7,000
       ↓
POLICY
       ↓
REVIEW / DENY
       ↓
NO AUTONOMOUS PAYMENT
```

### Scenario D — Payment failure

```text
GOVERNANCE = ALLOW
       ↓
RAZORPAY
       ↓
PAYMENT FAILED
       ↓
NO FULFILLMENT
       ↓
AUDIT + GRACEFUL RECOVERY
```

# 5. The final demo dashboard

For each transaction, show one page like:

```text
╔════════════════════════════════════════════════╗
║             PAARI TRANSACTION                  ║
║                TXN-001                         ║
╠════════════════════════════════════════════════╣
║ Buyer Agent       BA-001                        ║
║ Merchant Agent    MA-001                        ║
║ Quote             Q-001                         ║
║ Amount            ₹4,799                        ║
║                                                ║
║ GOVERNANCE                                      ║
║ ✓ Identity                                      ║
║ ✓ Authorization                                 ║
║ ✓ Merchant                                      ║
║ ✓ Quote                                         ║
║ ✓ Amount                                        ║
║ ✓ User Policy                                   ║
║ ✓ Autonomous Payment                            ║
║ ✓ Risk                                          ║
║                                                ║
║ DECISION: ALLOW                                 ║
║                                                ║
║ PAYMENT                                         ║
║ Session: PS-001                                 ║
║ Capability: CAP-001                             ║
║ Razorpay: VERIFIED                              ║
║                                                ║
║ FULFILLMENT: AUTHORIZED                         ║
╚════════════════════════════════════════════════╝
```

Then underneath:

```text
AUDIT TIMELINE

13:10:01  Quote accepted
13:10:02  Payment request received
13:10:02  Governance evaluated
13:10:02  Payment authorized
13:10:03  Razorpay order created
13:10:20  Payment received
13:10:21  Payment verified
13:10:21  Fulfillment authorized
```

Your current dashboard already exposes review and audit views, while the audit layer supports filtering by merchant, request, action, decision, and time.  

# 6. The single slide that explains Paari

I'd make the key message on the architecture slide:

> **Agents negotiate. Paari governs. Razorpay executes. Paari verifies. Merchant fulfills.**

And underneath:

```text
Every money action is:

EXPLAINABLE  → Why was it allowed or blocked?
BOUNDED      → Which transaction, amount, session and capability?
GATED        → Which policies and authorizations had to pass?
AUDITABLE    → What happened at every stage?
```

That is a much stronger showcase than simply showing a successful Razorpay payment.

Your existing implementation is already structured around exactly this separation: the runtime/LLM proposes actions, while the deterministic Gateway/Policy/Risk layers enforce them. 

**For the final presentation, I would therefore use 3 visuals in sequence: `Overall Architecture → End-to-End Data/Control Flow → 4 Test-Case Proofs`.** This lets someone understand what Paari is, see exactly how data moves, and then watch the governance claims being proven rather than merely asserted.

----------------------------------------

Not completely. The explanation in the screenshot is **partly correct, but the Razorpay conclusion is misleading**.

### Razorpay

The screenshot says:

> “Webhook log is empty because no real payment ever happens on Razorpay's side…”

That is **not quite true**.

Razorpay Test Mode does not process real money, but **test payments are still simulated as Razorpay transactions**, and Razorpay says Test Mode transactions can trigger the configured webhook events. ([Razorpay][1])

So the correct distinction is:

```text
Create Razorpay Order
        ↓
Order exists
        ↓
NO payment attempted
        ↓
No payment webhook
```

versus:

```text
Create Razorpay Order
        ↓
Complete a Test Payment
        ↓
payment.authorized / payment.captured / order.paid
        ↓
Webhook sent to your Paari backend
```

Razorpay specifically documents `payment.authorized`, `payment.captured`, and `order.paid` events for payment flows. ([Razorpay][2])

So **an empty webhook log can be perfectly normal if your current code only creates orders and never completes a test payment**.

Also, seeing GET requests in an API log does **not by itself prove** that only GETs happened. It depends on what log/filter you're looking at. Order creation itself is a server-side API operation, and subsequent GETs may simply be status/details lookups.

### Shopify

The screenshot's Shopify explanation is **plausible**, but I would not call it proven from the screenshot alone.

Creating a Shopify draft order and/or order with your Paari transaction ID, totals, and notes is a real Shopify-side operation. Shopify documents that draft orders can later be completed into orders. ([Shopify][3])

So:

```text
Paari
 ↓
Shopify order created
 ↓
Order exists
 ↓
Fulfillment API never called
 ↓
Order remains Unfulfilled
```

That is a technically valid explanation.

### For your Paari project, the real situation is probably this

```text
SHOPIFY
✅ Product/order data reaches Shopify
✅ Paari transaction information can be stored
✅ Order is created
❌ Fulfillment step not implemented yet
→ Unfulfilled
```

```text
RAZORPAY
✅ Test API credentials work
✅ Orders can be created
✅ Razorpay order IDs exist
❌ Test payment has not actually been completed
→ No payment-related webhook
```

The key test you should perform is:

```text
Paari authorization
      ↓
Create Razorpay test order
      ↓
Open Razorpay Test Checkout
      ↓
Actually complete a TEST payment
      ↓
payment.authorized
      ↓
payment.captured / order.paid
      ↓
Paari webhook endpoint
      ↓
Paari marks transaction PAID
      ↓
Shopify fulfillment/order-processing step
```

Also, Razorpay requires webhook URLs to be publicly reachable; `localhost` cannot directly receive Razorpay webhooks. ([Razorpay][1])

**So my verdict:**

**Razorpay statement: ~60–70% correct, but the wording “no payment ever happens on Razorpay's side” is wrong.** It should say **“no Test Mode payment was completed, so there was no payment event to send.”**

**Shopify statement: technically reasonable, but you need the actual Shopify order/API logs to confirm that the fulfillment call is the missing step.**

If you show me the **Razorpay API/webhook logs and Shopify order/API logs**, I can tell you exactly where your Paari flow currently stops.

[1]: https://razorpay.com/docs/webhooks/validate-test/?utm_source=chatgpt.com "Validate and Test Webhooks | Razorpay Docs"
[2]: https://razorpay.com/docs/webhooks/?utm_source=chatgpt.com "About Webhooks | Razorpay Docs"
[3]: https://shopify.dev/docs/api/admin-graphql/latest/mutations/draftordercreate?utm_source=chatgpt.com "draftOrderCreate - GraphQL Admin"

-----------------------------------------------

In your Paari architecture, the AI buyer agent should not directly “own” or call Razorpay with secret credentials. The agent requests a governed payment, Paari creates the bounded payment session/order, and the payment is completed through Razorpay Checkout. Razorpay requires an Order to be created server-side and passed to Checkout, and the successful Checkout response includes razorpay_payment_id, razorpay_order_id, and razorpay_signature. 

Your agentic payment flow

AI BUYER AGENT
      │
      │ "Pay for TXN-001"
      ▼
PAARI GATEWAY
      │
      ├─ Authenticate buyer
      ├─ Authorize payment
      ├─ Validate quote
      ├─ Validate amount
      ├─ Check user limits
      ├─ Check autonomy
      ├─ Check risk
      └─ Create bounded session/capability
      │
      ▼
RAZORPAY ORDER
      │
      ▼
RAZORPAY CHECKOUT
      │
      ▼
AI BUYER / PAYMENT UI
      │
      ▼
PAYMENT
      │
      ▼
Razorpay result + webhook
      │
      ▼
PAARI VERIFY
      │
      ▼
PAYMENT_VERIFIED

What the AI agent actually does

The Buyer Agent sends something like:

{
  "transaction_id": "TXN-001",
  "payment_session_id": "PS-001",
  "action": "EXECUTE_PAYMENT"
}

Paari checks that the session is active, belongs to the transaction, and covers the authorized amount. Then Paari creates/returns the Razorpay order_id.

Razorpay's standard flow is explicitly server-side Order creation followed by passing that order_id into Checkout. 

So your agent receives:

{
  "transaction_id": "TXN-001",
  "payment_session_id": "PS-001",
  "razorpay_order_id": "order_xxxxx",
  "authorized_amount": 4799,
  "currency": "INR"
}

Then who enters the payment details?

For a normal Razorpay Standard Checkout integration, the Checkout UI collects the payment information. The AI agent should not receive your Razorpay secret key. Razorpay documents test checkout as a mock payment page in Test Mode, where you can perform test payments without real money. 

For your Phase-1 demo, you can therefore have:

AI Buyer Agent
      ↓
Paari authorizes
      ↓
Razorpay Order
      ↓
Checkout
      ↓
Test payment

After payment

Razorpay returns:

razorpay_payment_id
razorpay_order_id
razorpay_signature

Your backend must verify the Checkout signature using:

HMAC-SHA256(
    order_id + "|" + razorpay_payment_id,
    key_secret
)

Razorpay specifically says to use the server-side stored order ID, not simply trust the razorpay_order_id returned by the client. 

Then separately process the Razorpay webhook:

Razorpay webhook
      ↓
HMAC webhook verification
      ↓
Paari transaction
      ↓
PAYMENT_VERIFIED

Razorpay recommends server-side signature verification and checking payment/order status before providing the service. 

For your Paari project, the key distinction is

AI Agent
    = requests / initiates payment

Paari
    = authorizes + bounds payment

Razorpay
    = executes payment

Paari
    = verifies payment

Merchant Agent
    = fulfills

So “agent makes payment” in Paari means the AI agent initiates and authorizes an agentic payment flow, not that the LLM gets a Razorpay secret key and independently transfers money.

For your current code, the next real-payment path should be:

Merchant Agent
 → final quote
 → Payment Request
 → Paari Governance
 → Payment Session + Capability
 → Razorpay Order
 → Checkout
 → Test Payment
 → Checkout Signature Verification
 → Razorpay Webhook Verification
 → PAYMENT_VERIFIED
 → Merchant Fulfillment

That is the cleanest and safest interpretation of AI agent making a payment in your Paari system.
-----------------------------------------------
Yes. That is the right interpretation for Paari.

The key distinction is:

LLM
  ≠ payment instrument

Paari
  = authorization + policy + risk + bounded execution

Razorpay
  = payment execution

Your current Phase 1 deliberately uses:

Human consent
      ↓
Razorpay Checkout
      ↓
Payment

while the future autonomous-payment extension would be:

Human
  ↓
Mandate / payment instrument enrollment
  ↓
Razorpay token / mandate
  ↓
Paari securely stores reference
  ↓
AI Buyer requests:
"Charge ₹X"
  ↓
Paari Gateway
  ├─ identity
  ├─ authorization
  ├─ mandate scope
  ├─ transaction/quote
  ├─ spending limit
  ├─ autonomous-payment policy
  ├─ session
  ├─ risk
  └─ audit
  ↓
ALLOW
  ↓
Razorpay API charge against authorized instrument
  ↓
Webhook verification
  ↓
Fulfillment

That would be a new payment capability, not a change to your existing governance architecture:

payment.request
        │
        │ Phase 1
        ▼
human checkout

payment.mandate_charge
        │
        │ future
        ▼
authorized instrument

The important design rule should remain:

> The AI agent receives authority to spend within a bounded mandate; it never receives the underlying payment credential.



What this means for Paari

Your current architecture is already suitable for this extension because your Gateway already enforces authentication → authorization → policy → risk → bounded payment state → audit, while the Payment Service owns the downstream payment integration. Your current implementation also already has one-time payment capabilities and 10-minute payment sessions.  

The future addition would therefore be roughly:

PAARI
                   │
        ┌──────────┴──────────┐
        │                     │
 payment.request      mandate_charge
        │                     │
 human checkout       pre-authorized instrument
                              │
                              ▼
                         Razorpay API

I would keep the current human-at-Checkout flow for your main demo. It is easier to explain, already proven end-to-end, and avoids expanding the scope of your showcase.

Then present autonomous mandate charging as Paari's Phase-3/production extension:

> Today: AI initiates a governed payment and the user completes Checkout.
Future: the user pre-authorizes a bounded payment instrument once, and Paari can safely allow the AI agent to charge within those predefined limits.



That gives Paari a credible evolution from agent-assisted payments → governed autonomous payments without weakening the core architecture.
-------------------------------------------------------------------------
For Paari, I would build autonomous agentic charging as a separate extension of the already-proven governance/payment architecture, not redesign the existing system.

Target architecture

USER
                   │
          One-time consent
          + payment enrollment
                   │
                   ▼
           RAZORPAY MANDATE /
           TOKENIZED INSTRUMENT
                   │
                   ▼
             PAARI VAULT
       (token/reference only)
                   │
                   ▼
              AI BUYER
                AGENT
                   │
             "Charge ₹X"
                   │
                   ▼
          ┌─────────────────┐
          │  PAARI GATEWAY  │
          └────────┬────────┘
                   │
       ┌───────────┼────────────┐
       ▼           ▼            ▼
    Identity      Policy       Risk
       │           │            │
       └───────────┼────────────┘
                   ▼
            Mandate Validation
                   │
            Transaction/Quote
                   │
            Session/Capability
                   │
              ALLOW / REVIEW / DENY
                   │
                   ▼
          RAZORPAY API CHARGE
                   │
                   ▼
              WEBHOOK
                   │
                   ▼
          PAARI VERIFICATION
                   │
                   ▼
              FULFILLMENT
                   │
                   ▼
                AUDIT

Your current design already provides the governance, risk, session/capability, payment, webhook and audit foundations needed for this extension.  

Phase 1 — Mandate enrollment

Do not start with AI charging.

First build the human-consent flow.

USER
 ↓
"Allow Paari to make autonomous purchases"
 ↓
Razorpay enrollment / mandate setup
 ↓
User authenticates
 ↓
Mandate created
 ↓
Paari stores mandate reference

Paari's database should store something like:

{
  "mandate_id": "MAND-001",
  "user_id": "USER-001",
  "provider": "RAZORPAY",
  "instrument_reference": "provider_ref",
  "status": "ACTIVE"
}

Do not store raw card credentials in Paari.

Your exact Razorpay product/API for mandate setup should be chosen from the payment method and current Razorpay account capabilities; verify this against the current Razorpay documentation before implementing the live path.

Phase 2 — Define mandate policy

The mandate must have explicit boundaries.

Example:

{
  "mandate_id": "MAND-001",

  "max_per_transaction": 5000,
  "daily_limit": 10000,

  "allowed_merchants": [
    "MER-001"
  ],

  "allowed_categories": [
    "FOOTWEAR"
  ],

  "autonomous_payment": true,

  "requires_review_above": 3000,

  "expires_at": "..."
}

Now your effective authority becomes:

User consent
   +
Mandate limits
   +
Paari policy
   +
Merchant policy
   +
Transaction

The agent cannot expand any of these limits.

Phase 3 — Add a new capability

Keep your existing:

payment.request

and introduce a distinct high-risk capability:

payment.mandate_charge

Example:

{
  "capability": "payment.mandate_charge",
  "mandate_id": "MAND-001",
  "max_amount": 5000,
  "usage": "BOUNDED_REUSABLE"
}

This is much better than allowing:

payment.execute

to mean everything.

Phase 4 — Create a mandate-charge transaction

When the Buyer Agent decides:

> "Buy the approved product for ₹2,499."



it sends:

{
  "action": "MANDATE_CHARGE",
  "buyer_agent_id": "BA-001",
  "merchant_id": "MER-001",
  "quote_id": "Q-001",
  "mandate_id": "MAND-001",
  "amount": 2499,
  "currency": "INR"
}

Paari creates:

TXN-2001

and does not immediately call Razorpay.

Phase 5 — Run the normal Paari governance pipeline

Reuse your existing governance engine.

MANDATE_CHARGE
      ↓
Buyer identity
      ↓
Buyer authorization
      ↓
Merchant authorization
      ↓
Quote validation
      ↓
Amount match
      ↓
User limit
      ↓
Mandate validity
      ↓
Mandate amount limit
      ↓
Autonomous payment policy
      ↓
Risk
      ↓
ALLOW / REVIEW / DENY

Your current governance model already aggregates decisions as DENY > REVIEW > ALLOW, audits checks and transitions transaction state. 

Phase 6 — Add the new mandate checks

Create specific rules:

mandate_exists
mandate_active
mandate_owner_matches_user
merchant_allowed_by_mandate
amount_within_mandate_limit
daily_mandate_limit
category_allowed
mandate_not_expired

For example:

Transaction = ₹4,000
Mandate maximum = ₹5,000
             ↓
PASS

But:

Transaction = ₹7,000
Mandate maximum = ₹5,000
             ↓
DENY

Phase 7 — Use a bounded charge authorization

After ALLOW:

Governance
    ↓
Charge Authorization
    ↓
mandate_id
transaction_id
authorized_amount
currency
expires_at

Example:

{
  "authorization_id": "AUTH-5001",
  "transaction_id": "TXN-2001",
  "mandate_id": "MAND-001",
  "authorized_amount": 2499,
  "currency": "INR",
  "expires_at": "..."
}

This is the autonomous equivalent of your current one-time payment capability.

Phase 8 — Create a dedicated mandate-charge execution path

Don't overload your existing human Checkout endpoint.

Create something like:

POST /payments/mandate-charge

Input:

{
  "transaction_id": "TXN-2001",
  "authorization_id": "AUTH-5001"
}

Internally:

Load transaction
      ↓
Load authorization
      ↓
Validate transaction state
      ↓
Validate mandate
      ↓
Validate authorization amount
      ↓
Validate not expired
      ↓
Validate unused/idempotency
      ↓
Razorpay charge

This should be the only path that can perform autonomous charging.

Phase 9 — Idempotency becomes mandatory

This is even more important for autonomous payments.

Suppose the AI agent retries:

Charge ₹2,499
Charge ₹2,499

Paari must ensure only one charge occurs.

Use:

idempotency_key
transaction_id
mandate_id
charge_authorization_id

and enforce:

same transaction + same authorization
      ↓
same result

Your existing A2A system already has an idempotency-key concept, so reuse the same principle. 

Phase 10 — Razorpay execution

Only after all checks:

Paari
 ↓
MANDATE_CHARGE ALLOW
 ↓
Razorpay API
 ↓
Charge authorized instrument

The key rule remains:

LLM → never sees payment credential
Paari → controls authorization
Razorpay → executes payment

Phase 11 — Two-layer verification remains

Keep your existing model:

Layer 1
Provider API response / charge validation

Layer 2
Razorpay webhook
      ↓
HMAC verification
      ↓
payment event

Then:

PAYMENT_VERIFIED

Your current architecture already uses verified Razorpay events to transition payment state and prevent unverified fulfillment. 

Phase 12 — Settlement

Reuse your existing settlement helper:

PAYMENT_VERIFIED
      ↓
settle_verified_transaction()
      ↓
Merchant Agent
      ↓
Shopify

Your latest implementation already centralizes verified settlement and guards against duplicate Shopify orders. 

Phase 13 — Audit the mandate itself

For autonomous payment, your audit should show:

MANDATE_CREATED
MANDATE_ACTIVATED
MANDATE_POLICY_LOADED
MANDATE_CHARGE_REQUESTED
MANDATE_VALIDATED
GOVERNANCE_ALLOWED
CHARGE_AUTHORIZED
RAZORPAY_CHARGE_REQUESTED
RAZORPAY_PAYMENT_CONFIRMED
FULFILLMENT_AUTHORIZED

Dashboard:

AUTONOMOUS PAYMENT

User:
USER-001

Mandate:
MAND-001

Transaction:
TXN-2001

Requested:
₹2,499

Mandate limit:
₹5,000

Daily remaining:
₹7,501

Merchant:
MER-001

Decision:
ALLOW

Reason:
✓ Mandate active
✓ Agent authorized
✓ Merchant allowed
✓ Quote matches
✓ Within mandate limit
✓ Within daily limit
✓ Autonomous payment enabled
✓ Risk acceptable

Payment:
VERIFIED

Phase 14 — Test it before live Razorpay

Build these tests first.

A — valid autonomous charge

Mandate = ₹5,000
Transaction = ₹2,499
→ ALLOW
→ charge
→ VERIFIED

B — mandate limit exceeded

Mandate = ₹5,000
Transaction = ₹7,000
→ DENY
→ no Razorpay call

C — merchant not allowed

Mandate allows MER-001
Transaction targets MER-999
→ DENY

D — mandate expired

Mandate expired
→ DENY

E — daily limit exceeded

Daily used = ₹9,000
Daily limit = ₹10,000
New charge = ₹2,000
→ DENY

F — duplicate request

same transaction
same mandate
same authorization
two requests
→ one charge only

G — suspicious transaction

Governance passes
Risk = HIGH
→ REVIEW
→ no charge until approved

H — payment failure

Governance = ALLOW
Razorpay = FAILED
→ PAYMENT_FAILED
→ no fulfillment

Phase 15 — Roll it into your existing capability model

Your capability system becomes:

PAYMENT CAPABILITIES

payment.request
       │
       └── Human-assisted payment

payment.mandate_charge
       │
       └── Autonomous bounded payment

This is much clearer than making payment.execute do both jobs.

Final architecture

USER
                           │
                    ONE-TIME CONSENT
                           │
                           ▼
                    RAZORPAY MANDATE
                           │
                           ▼
                      PAARI MANDATE
                         POLICY
                           │
                           ▼
                    AI BUYER AGENT
                           │
                    "CHARGE ₹2,499"
                           │
                           ▼
                 ┌──────────────────┐
                 │   PAARI GATEWAY  │
                 └────────┬─────────┘
                          │
             ┌────────────┼────────────┐
             ▼            ▼            ▼
          Identity       Policy       Risk
             │            │            │
             └────────────┼────────────┘
                          ▼
                  Mandate validation
                          │
                  Transaction validation
                          │
                  Session/Capability
                          │
                   ALLOW / REVIEW / DENY
                          │
                        ALLOW
                          │
                          ▼
                RAZORPAY API CHARGE
                          │
                          ▼
                     WEBHOOK
                          │
                          ▼
                 PAARI VERIFICATION
                          │
                          ▼
                  PAYMENT_VERIFIED
                          │
                          ▼
                     SETTLEMENT
                          │
                          ▼
                   MERCHANT AGENT
                          │
                          ▼
                       SHOPIFY

Recommended development sequence

1. Mandate data model
        ↓
2. Mandate policy model
        ↓
3. payment.mandate_charge capability
        ↓
4. Mandate governance rules
        ↓
5. Charge authorization object
        ↓
6. /payments/mandate-charge
        ↓
7. Idempotency protection
        ↓
8. Razorpay mandate/token integration
        ↓
9. Webhook verification
        ↓
10. Existing settlement
        ↓
11. Audit + dashboard
        ↓
12. Full autonomous-payment test suite

The key architectural decision is to reuse your existing Paari Governance Engine rather than create a second autonomous-payment governance system. Your current Gateway already provides the enforcement path, and the new mandate capability becomes another tightly bounded financial action going through the same governance, risk, state, audit, and verification controls. 

One caveat: before implementing the Razorpay-specific mandate API calls, verify the exact currently supported Razorpay mandate/token product and API flow for your intended payment instrument and account; the Paari architecture above is the stable part, while that provider-specific execution interface can vary.

---------------------------------------------------------------------------------
Exploration done. Here is the expert plan — validated against the repo, with corrections to the pasted proposal where the codebase says otherwise.
Mandate-charge extension — implementation plan
Standing constraints (from repo): DENY > REVIEW > ALLOW, rules evaluate in RULE_PIPELINE order, audit fail-closed, extra="forbid" on schemas, strict mypy, tests offline. Note: this deliberately expands architecture (new tables/endpoint/capability) — treat as approved scope exception.
Phase 0 — Corrections to the pasted proposal (codebase facts)
1. Don't build a second governance system — confirmed reusable. Rules register by append in rules/__init__.py:21-31, signature check(context) -> CheckResult. One new rule file, not eight: rules/mandate.py emitting granular reason_codes (MANDATE_MISSING/INACTIVE/OWNER_MISMATCH/MERCHANT_BLOCKED/AMOUNT_EXCEEDED/DAILY_EXCEEDED/EXPIRED).
2. Daily limits are an empty slot, not a new concept. user_spending.py:9-28 enforces only per-tx max; daily_spending_limit is loaded (context.py:73-81) and seeded but never read by any rule. Mandate daily accounting fills a real gap — design it so user-level daily enforcement can follow the same pattern later.
3. Don't invent idempotency — idempotency_keys table already exists (init.sql:242-250, PK on key). Reuse it.
4. Don't widen payment_capabilities.usage to reusable. Keep the proven one-time model: one charge authorization row per mandate charge (action="mandate.charge", single-use). Reusable capabilities weaken the bounded-execution proof.
5. Copy the checkout schema pattern, not the create one. CreatePaymentRequest is missing extra="forbid" (known bug) — the new mandate-charge schema must include it.
6. Razorpay adapter has zero mandate/token support (razorpay_live.py:19-201: only order/verify/fetch/capture). Provider interface stays abstract behind stub-first; live wiring gated on docs verification (your caveat stands).
Phase 1 — Data model (db/init.sql, seed, migration)
- New mandates table: id, display_id UNIQUE, user_id→users, provider, instrument_reference (opaque, never raw PAN), status ACTIVE/REVOKED/EXPIRED, max_per_transaction, daily_limit, allowed_merchants_json, allowed_categories_json, autonomous_enabled, requires_review_above, expires_at, created_at. CREATE TABLE IF NOT EXISTS + column checks (repo migration convention).
- New mandate_daily_usage table: (mandate_id, day, used_paise) — atomic increment on charge; payment_events.payload_json has no amount column, so don't try to aggregate from it.
- Seed MAND-001 for USER-001 (max 5,000 / daily 10,000 / merchants [MER-001] / review-above 3,000) mirroring seed.py:244-251 style.
Phase 2 — Capability (schemas/capability.py, authz/*, seed.py)
- Add PAYMENT_MANDATE_CHARGE = "payment.mandate_charge" to the Capability enum (capability.py:10-24).
- Grant to buyer agent in seed; extend rules/agent_authorization.py:12 so the mandate flow accepts payment.mandate_charge as an alternative to payment.request (without weakening the human-checkout path, which keeps requiring payment.request).
Phase 3 — Governance rule (governance_engine/rules/mandate.py)
- Single check() following buyer_credential.py:26-48 structure: pass-through PASS when tx carries no mandate_id (human-checkout flows unaffected); otherwise validate exists → active → owner (agent.owner_id) → merchant/category allow-list → amount → daily (mandate_daily_usage) → expiry. FAIL on violations, REVIEW when amount > requires_review_above.
- Register in RULE_PIPELINE after user_spending, before autonomous_payment (so mandate bounds read before the autonomy threshold; outcome order-independent under DENY-wins, audit trail ordered).
- Reuse autonomous_payment.py:24-33 untouched for the human-confirmation threshold.
Phase 4 — Service + endpoint (mirror the proven pair)
- PaymentService.authorize_mandate_charge() mirroring authorize_payment() (service.py:276-345): context load → evaluate → DENY→DENIED, REVIEW→REVIEW_REQUIRED, ALLOW→AUTHORIZED→PAYMENT_PENDING + session + one-time mandate.charge capability row.
- POST /payments/mandate-charge (api/payments.py style, extra="forbid"): input {transaction_id, authorization_id, mandate_id, idempotency_key}; validates session active + tx match + amount equality (same typed-reason discipline as create_razorpay_order: session_not_found|not_active|tx_mismatch|amount_mismatch|mandate_*) with no adapter call on failure; checks idempotency_keys first (same tx+auth → replay stored result); increments mandate_daily_usage; calls provider charge_mandate(); records payment_events.
- Provider interface on the adapter (charge_mandate(mandate_ref, amount, currency)): stub implements deterministic approve/decline; live raises NotImplemented until the Razorpay mandate product is verified against current docs.
Phase 5 — Reuse verification/settlement/audit unchanged
- payment.captured/order.paid → existing handler → settle_verified_transaction() → merchant fulfill. No changes; mandate charges flow through the identical trust boundary.
- Audit: existing per-check rows + a MANDATE_POLICY_LOADED detail inside the mandate check's details (no new audit plumbing; fail-closed write already covers it).
Phase 6 — Tests (TDD, offline, mirroring proposal's A–H)
- tests/test_mandate.py: rule matrix (each reason_code), capability accept/reject, daily-limit accounting across two charges, expired/revoked/merchant-block → DENY with no adapter call asserted, idempotent replay (same key → one charge), HIGH-risk + REVIEW → no charge, PAYMENT_FAILED → no fulfill.
- Live-adapter mandate tests gated by key presence, following test_razorpay_live.py convention.
Sequencing
DB/migration → capability+seed → rule (+pipeline slot) → service+endpoint → stub provider → settle wiring (no-op code, verify path) → tests per phase → docs (BACKEND_INTEGRATION.md amendment) → full suite → restart.
Two scoping questions:
How much of the mandate extension should be built?
1.
Full extension
All 6 phases: tables, capability, rule, endpoint, stub provider, tests
2.
Governance slice only
Mandate tables + rule + tests, no charge endpoint yet
3.
Spike first
Rule + stub charge path only, minimal tables
4.
Type your own answer
---------
How should mandate enrollment (human consent step) be exposed?
1.
API only
POST endpoint creating mandate rows, UI later
2.
API + seed demo
Endpoint plus seeded MAND-001 for instant demo
3.
Defer enrollment
Assume mandates exist, build charging only
4.
Type your own answer

I would choose 1. Full extension and 2. API + seed demo.

That gives you a complete, testable autonomous-payment capability without creating a second governance architecture:

Mandate enrollment
      ↓
MAND-001
      ↓
AI Buyer requests mandate.charge
      ↓
Existing Paari Governance Engine
      ↓
Mandate rule + existing policy/risk checks
      ↓
ALLOW / REVIEW / DENY
      ↓
One-time mandate.charge capability
      ↓
Idempotent charge
      ↓
Provider adapter
      ↓
Existing verification / settlement / audit

Why Full extension

It lets you validate the complete concept rather than only the rule:

Human consent
    ↓
Mandate
    ↓
Governed autonomous request
    ↓
Bounded execution
    ↓
Verification
    ↓
Fulfillment

It also preserves your existing architecture: the proposal correctly says to add one mandate rule, reuse idempotency_keys, keep payment capabilities single-use, and leave the existing human-checkout path unchanged.

Why API + seed demo

For the enrollment phase:

POST /mandates

plus:

MAND-001
USER-001
₹5,000 / transaction
₹10,000 / day
MER-001 allowed
₹3,000 review threshold

This gives you both:

Real API architecture
        +
Instant reproducible demo

You can test charging immediately without building UI enrollment yet.

One refinement to the plan

Keep the provider abstraction exactly as proposed:

Paari
  ↓
charge_mandate(...)
  ↓
Stub provider

and do not implement the live Razorpay mandate call until the exact supported Razorpay mandate/token product and API contract are verified.

So the implementation sequence should be:

1. Mandate DB + migration
2. Mandate enrollment API + MAND-001 seed
3. payment.mandate_charge capability
4. mandate governance rule
5. mandate-charge authorization service
6. /payments/mandate-charge
7. Idempotency + daily usage accounting
8. Stub charge provider
9. Existing verification/settlement/audit
10. Full offline test suite
11. Live Razorpay mandate integration after provider verification

This is the right next extension for Paari because the existing governance engine remains the single authority; autonomous mandate charging simply becomes another high-risk financial capability that must pass through the same control plane.
---------------------------------------------------------------
Final plan — mandate-based autonomous charging (locked)
Decisions locked: full extension + enrollment API with seeded demo mandate. No second governance system; single Paari control plane remains the sole authority.
Objective
A complete, testable autonomous-payment capability: human consents once → mandate exists → AI buyer requests mandate.charge → existing governance allows/denies → bounded one-time execution → existing verification/settlement/audit. Human-checkout path untouched.
Standing constraints
DENY > REVIEW > ALLOW · rules run in RULE_PIPELINE order · audit fail-closed · extra="forbid" on all new schemas · strict mypy · tests offline · Postgres-compatible DDL with IF NOT EXISTS · no raw credential storage (opaque instrument_reference only).
Build sequence
1. Mandate DB + migration (paari/db/init.sql + migration)
- mandates: id, display_id UNIQUE, user_id→users, provider, instrument_reference, status (ACTIVE/REVOKED/EXPIRED), max_per_transaction, daily_limit, allowed_merchants_json, allowed_categories_json, autonomous_enabled, requires_review_above, expires_at, created_at
- mandate_daily_usage: (mandate_id, day, used_paise) — atomic increment per charge (amounts not derivable from payment_events.payload_json)
2. Enrollment API + seed 
- POST /mandates/enroll: {user_id, provider, instrument_reference, max_per_transaction, daily_limit, allowed_merchants, allowed_categories, requires_review_above, expires_at} → validates user exists + max ≤ daily → writes ACTIVE row → audits MANDATE_CREATED/ACTIVATED. Human-authenticated (dashboard session or buyer JWT).
- Seed MAND-001 → USER-001, ₹5,000/tx, ₹10,000/day, [MER-001], review above ₹3,000 (mirrors seed.py:244-251 style) for instant demo without UI.
3. Capability (schemas/capability.py, authz/*, seed.py)
- PAYMENT_MANDATE_CHARGE = "payment.mandate_charge"; grant to buyer agent; agent_authorization.py:12 accepts it as an alternative to payment.request on the mandate path only.
4. Governance rule (governance_engine/rules/mandate.py, one file)
- check() per buyer_credential.py:26-48 structure: pass-through PASS when tx has no mandate_id; else exists → active → owner → merchant/category allow-list → amount → daily → expiry. FAIL on violation, REVIEW above requires_review_above. Registered after user_spending, before autonomous_payment (untouched).
5. Authorization service (payment/service.py)
- authorize_mandate_charge() mirroring authorize_payment() (:276-345): context → evaluate → DENIED/REVIEW_REQUIRED/AUTHORIZED→PAYMENT_PENDING + session + one-time mandate.charge capability row.
6. Charge endpoint (POST /payments/mandate-charge)
- Input {transaction_id, authorization_id, mandate_id, idempotency_key}; typed-reason validation (session_not_found|not_active|tx_mismatch|amount_mismatch|mandate_*), no adapter call on failure; idempotency check first via existing idempotency_keys; increment daily usage; call provider; record payment_events.
7. Provider abstraction
- Adapter method charge_mandate(ref, amount, currency) — stub implements deterministic approve/decline; live raises NotImplemented until the exact Razorpay mandate/token product and API contract are verified against current docs.
8. Reuse unchanged: payment.captured/order.paid handler → settle_verified_transaction() → merchant fulfill; audit rows as today.
9. Tests (tests/test_mandate.py, offline): rule matrix per reason_code · capability accept/reject · daily accounting over two charges · expired/revoked/merchant-block → DENY with no-adapter-call asserted · idempotent replay → single charge · HIGH-risk REVIEW → no charge · PAYMENT_FAILED → no fulfill · live tests key-gated per repo convention.
10. Docs + suite + restart: BACKEND_INTEGRATION.md amendment, full suite green, server restart.
Non-goals
Live Razorpay mandate calls · raw PAN/token-vault design (deferred to security review) · any change to human-checkout, risk engine, seed hours, or existing rules.
Awaiting your go-ahead to execute.