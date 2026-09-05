export interface TransactionStep {
  seq: number;
  type: string;
  title: string;
  time: string;
  desc: string;
  description?: string;
  timestamp?: string;
  status: "passed" | "active" | "pending" | "failed";
  decision?: "ALLOW" | "DENY";
  provider?: "razorpay" | "shopify";
  payment_status?: "success" | "pending" | "failed";
}

export interface Transaction {
  txn_id: string;
  quote_id: string;
  status: "in_progress" | "success" | "failed";
  current_step: number;
  started_at: string;
  ended_at: string;
  duration_seconds: number;
  steps: TransactionStep[];
}

export interface TransactionSummary {
  id: string;
  txn_id: string;
  quote_id: string;
  state: string;
  status: "in_progress" | "success" | "failed";
  amount_paise: number;
  currency: string;
  created_at: string;
}

export interface AuditCheckpoints {
  passed: number;
  total: number;
  label: string;
}

export interface AuditDetail extends Transaction {
  state: string;
  amount_paise: number;
  currency: string;
  decision: string;
  checkpoints: AuditCheckpoints;
  status_note: string;
  reason?: string | null;
  failed_checks?: string[];
  review_checks?: string[];
  razorpay_order_id?: string | null;
  razorpay_payment_id?: string | null;
  digest: string;
  immutable: boolean;
}

export interface ConnectionDetails {
  store_name?: string;
  webhook_status?: string;
  last_sync?: string;
  orders_today?: number;
  fulfillment_rate?: number;
  buyer_agents_online?: number;
  merchant_agents_online?: number;
  queue?: number;
  last_activity?: string;
  services_online?: number;
  services_total?: number;
  policies_enforced?: number;
  transactions_today?: number;
  avg_decision_time_ms?: number;
  model?: string;
  provider?: string;
  avg_response_time_ms?: number;
  requests_today?: number;
  error_rate?: number;
  success_rate?: number;
  pending_payments?: number;
  mode?: string;
  // Payment Gateway — bounded payment for the current transaction
  sessions_bound_total?: number;
  sessions_active?: number;
  avg_verification_time_ms?: number;
  session_bound?: boolean;
  transaction_id?: string;
  transaction_state?: string;
  currency?: string;
  razorpay_order_id?: string;
  session_id?: string;
  session_status?: string;
  authorized_amount_paise?: number;
  session_expires_at?: string;
  capability_id?: string;
  capability_action?: string;
  capability_usage?: string;
  capability_used?: number;
  capability_max_paise?: number;
}

export interface Connection {
  id: string;
  name: string;
  status: string;
  mode?: string;
  details: ConnectionDetails;
}

export interface HealthMetric {
  online?: number;
  total?: number;
  ok?: number;
  label: string;
  status?: string;
  type?: string;
  percent?: number;
  days?: number;
}

export interface Health {
  status: "healthy" | "degraded" | "down";
  metrics: {
    services: HealthMetric;
    webhooks: HealthMetric;
    database: HealthMetric;
    uptime: HealthMetric;
  };
  alerts: Array<{ severity: string; message: string; timestamp: string }>;
}

// Merchant-scoped token slot. The buyer console (/buyer, autorun scenarios)
// uses a DIFFERENT key, so the merchant identity stored here can never be
// reused by a buyer flow (a merchant token fails governance with
// MISSING_CAPABILITY because merchants lack payment.request).
const TOKEN_KEY = "paari_access_token_merchant";

let authPromise: Promise<string> | null = null;

export function getStoredToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function storeToken(token: string): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem(TOKEN_KEY);
}

function getAuthHeaders(token: string): Record<string, string> {
  return { Authorization: `Bearer ${token}` };
}

async function ensureAuthToken(): Promise<string> {
  const existing = getStoredToken();
  if (existing) return existing;

  if (authPromise) return authPromise;

  authPromise = postMerchantToken()
    .then((data) => {
      storeToken(data.access_token);
      return data.access_token;
    })
    .finally(() => {
      authPromise = null;
    });

  return authPromise;
}

export async function postMerchantToken(): Promise<{ access_token: string; agent: { role: string } }> {
  const res = await fetch("/api/auth/agent-token", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ agent_type: "merchant", agent_id: "MA-001" }),
  });
  if (!res.ok) {
    throw new Error("Auth failed");
  }
  return res.json();
}

async function authFetch(
  url: string,
  options: RequestInit = {}
): Promise<Response> {
  let token = getStoredToken() ?? (await ensureAuthToken());

  const makeRequest = (t: string) =>
    fetch(url, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...getAuthHeaders(t),
        ...options.headers,
      },
    });

  let res = await makeRequest(token);

  if (res.status === 401) {
    clearToken();
    token = await ensureAuthToken();
    res = await makeRequest(token);
  }

  return res;
}

export async function getTransactionsCurrent(): Promise<Transaction> {
  const res = await authFetch("/api/transactions/current");
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}`);
  }
  return res.json();
}

export async function getTransactions(): Promise<TransactionSummary[]> {
  const res = await authFetch("/api/transactions");
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}`);
  }
  const data = await res.json();
  return (data.transactions ?? []).map((t: Record<string, unknown>) => ({
    id: (t.id as string) ?? (t.txn_id as string),
    txn_id: t.txn_id as string,
    quote_id: (t.quote_id as string) ?? "",
    state: t.state as string,
    status: t.status as TransactionSummary["status"],
    amount_paise: t.amount_paise as number,
    currency: (t.currency as string) ?? "INR",
    created_at: (t.created_at as string) ?? "",
  }));
}

export async function getAuditDetail(txnId: string): Promise<AuditDetail> {
  const res = await authFetch(`/api/audit/${encodeURIComponent(txnId)}`);
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}`);
  }
  return res.json();
}

export async function getConnection(id: string): Promise<Connection> {
  const res = await authFetch(`/api/connections/${id}`);
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}`);
  }
  return res.json();
}

export async function getConnections(): Promise<Connection[]> {
  const res = await authFetch("/api/connections");
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}`);
  }
  const data = await res.json();
  return (data.connections ?? []).map((conn: Record<string, unknown>) => ({
    id: conn.id as string,
    name: conn.name as string,
    status: conn.status as string,
    mode: conn.mode as string | undefined,
    details: (conn.rows as Record<string, string | number> | undefined) ?? {},
  }));
}

export async function getHealth(): Promise<Health> {
  const res = await authFetch("/api/health");
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}`);
  }
  return res.json();
}
