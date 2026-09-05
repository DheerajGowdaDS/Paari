"""GraphQL queries for the Shopify Admin API."""

from __future__ import annotations

# ── Product / Catalog ──────────────────────────────────────────────

SEARCH_PRODUCTS = """
query SearchProducts($query: String!, $first: Int!) {
  products(query: $query, first: $first) {
    edges {
      node {
        id
        title
        description
        productType
        tags
        variants(first: 10) {
          edges {
            node {
              id
              sku
              price
              inventoryQuantity
            }
          }
        }
      }
    }
  }
}
"""

GET_PRODUCT_BY_SKU = """
query GetProductBySku($sku: String!) {
  productByHandle(handle: $sku) {
    id
    title
    description
    productType
    tags
    variants(first: 10) {
      edges {
        node {
          id
          sku
          price
          inventoryQuantity
        }
      }
    }
  }
}
"""

# ── Inventory ──────────────────────────────────────────────────────

GET_INVENTORY_LEVELS = """
query GetInventoryLevels($variantId: ID!) {
  productVariant(id: $variantId) {
    id
    inventoryItem {
      id
      inventoryLevels(first: 10) {
        edges {
          node {
            quantities(names: ["available"]) {
              name
              quantity
            }
          }
        }
      }
    }
  }
}
"""

# ── Price ──────────────────────────────────────────────────────────

GET_VARIANT_PRICE = """
query GetVariantPrice($variantId: ID!) {
  productVariant(id: $variantId) {
    id
    sku
    price
    compareAtPrice
  }
}
"""

# ── Draft Orders ───────────────────────────────────────────────────

CREATE_DRAFT_ORDER = """
mutation CreateDraftOrder($input: DraftOrderInput!) {
  draftOrderCreate(input: $input) {
    draftOrder {
      id
      status
    }
    userErrors {
      field
      message
    }
  }
}
"""

COMPLETE_DRAFT_ORDER = """
mutation CompleteDraftOrder($draftOrderId: ID!) {
  draftOrderComplete(id: $draftOrderId) {
    draftOrder {
      id
      order {
        id
        name
        createdAt
      }
    }
    userErrors {
      field
      message
    }
  }
}
"""

# Direct order creation — used when the access token lacks write_draft_orders
# scope (draftOrderCreate returns ACCESS_DENIED). Requires write_orders scope.
CREATE_ORDER = """
mutation CreateOrder($order: OrderCreateOrderInput!) {
  orderCreate(order: $order) {
    order {
      id
      name
      displayFinancialStatus
      displayFulfillmentStatus
    }
    userErrors {
      field
      message
    }
  }
}
"""

# ── Webhooks ───────────────────────────────────────────────────────

CREATE_WEBHOOK_SUBSCRIPTION = """
mutation CreateWebhookSubscription($topic: WebhookSubscriptionTopic!, $callbackUrl: URL!) {
  webhookSubscriptionCreate(
    topic: $topic
    webhookSubscription: {callbackUrl: $callbackUrl, format: JSON}
  ) {
    webhookSubscription {
      id
      topic
      callbackUrl
    }
    userErrors {
      field
      message
    }
  }
}
"""

DELETE_WEBHOOK_SUBSCRIPTION = """
mutation DeleteWebhookSubscription($id: ID!) {
  webhookSubscriptionDelete(id: $id) {
    deletedWebhookSubscriptionId
    userErrors {
      field
      message
    }
  }
}
"""

# ── Pages (policy fallback) ────────────────────────────────────────

GET_PAGES = """
query GetPages($first: Int!) {
  pages(first: $first) {
    edges {
      node {
        id
        title
        bodySummary
        handle
      }
    }
  }
}
"""
