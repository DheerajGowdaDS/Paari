export interface BuyerChatRequest {
  session_id: string;
  message: string;
  context?: { agent_id: string };
}

export interface BuyerChatResponse {
  session_id: string;
  reply: {
    text: string;
    products?: {
      name: string;
      description: string;
      availability_label: string;
      price_label?: string;
    }[];
    quote?: { quote_id: string; status_label: string };
    order?: { order_label: string };
    decision: "ALLOW" | "REVIEW" | "DENY";
    decision_note?: string;
  };
  suggestions: { label: string; prompt: string }[];
  actions: ("inspect_terms" | "ask_followup")[];
}

export interface EscrowAuthorizeRequest {
  quote_id: string;
}

export interface EscrowAuthorizeResponse {
  status: "queued" | "confirmed" | "needs_review";
  message: string;
}

export interface TermsResponse {
  title: string;
  body: string;
}

export type AutorunEventType =
  | "llm"
  | "tool"
  | "governance"
  | "payment"
  | "payment_verified"
  | "fulfillment"
  | "done"
  | "aborted";

export interface AutorunEvent {
  seq: number;
  type: AutorunEventType;
  text: string;
  status?: "active" | "passed" | "pending" | "failed";
  decision?: "ALLOW" | "REVIEW" | "DENY" | "FAILED";
  tool?: string;
  products?: Array<{
    name: string;
    description: string;
    availability_label: string;
  }>;
  quote?: { quote_id: string; status_label: string };
  txn_id?: string;
  quote_id?: string;
  timestamp?: string;
  time_ist?: string;
}

export interface AutorunAbortResponse {
  status: "aborted";
  message: string;
  session_id: string;
}

export interface AutorunPollResponse {
  session_id: string;
  txn_id: string;
  quote_id: string;
  events: AutorunEvent[];
}

export interface AgentTokenRequest {
  agent_type: string;
  agent_id: string;
}

export interface AgentTokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  agent: {
    agent_id: string;
    role: string;
    label: string;
  };
}

// Buyer-scoped token slot. The merchant console (/merchant, /audit) uses a
// DIFFERENT key, so opening the merchant page can never overwrite the buyer
// identity used by /buyer and the autorun scenarios (each role needs its own
// capabilities to pass governance).
const TOKEN_KEY = "paari_access_token_buyer";

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

function getAuthHeaders(): Record<string, string> {
  const token = getStoredToken();
  console.log("[buyerApi] getAuthHeaders - token exists:", !!token, token ? token.substring(0, 30) + "..." : "null");
  if (token) {
    return { Authorization: `Bearer ${token}` };
  }
  return {};
}

export async function postAgentToken(
  body: AgentTokenRequest
): Promise<AgentTokenResponse> {
  const res = await fetch("/api/auth/agent-token", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: "Auth failed" }));
    throw new Error(error.detail || "Auth failed");
  }
  return res.json();
}

export async function getAuthMe(): Promise<{ agent: { role: string } }> {
  const res = await fetch("/api/auth/me", {
    method: "GET",
    headers: { "Content-Type": "application/json", ...getAuthHeaders() },
  });
  if (!res.ok) {
    throw new Error("Not authenticated");
  }
  return res.json();
}

export async function postBuyerChat(
  body: BuyerChatRequest
): Promise<BuyerChatResponse> {
  const headers = {
    "Content-Type": "application/json",
    ...getAuthHeaders(),
  };
  console.log("[buyerApi] postBuyerChat headers:", JSON.stringify(headers));
  const res = await fetch("/api/agent/buyer/chat", {
    method: "POST",
    headers,
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({ error: { message: "Request failed" } }));
    const errorMessage =
      errorData?.error?.message || `HTTP ${res.status}`;
    throw new Error(errorMessage);
  }
  return res.json();
}

export async function postEscrowAuthorize(
  body: EscrowAuthorizeRequest
): Promise<EscrowAuthorizeResponse> {
  const res = await fetch("/api/escrow/authorize", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...getAuthHeaders(),
    },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({ error: { message: "Escrow failed" } }));
    const errorMessage =
      errorData?.error?.message || `HTTP ${res.status}`;
    throw new Error(errorMessage);
  }
  return res.json();
}

export async function getTerms(): Promise<TermsResponse> {
  const res = await fetch("/api/terms", {
    method: "GET",
    headers: { "Content-Type": "application/json", ...getAuthHeaders() },
  });
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}`);
  }
  return res.json();
}

let authPromise: Promise<string> | null = null;

async function ensureAuthToken(): Promise<string> {
  const existing = getStoredToken();
  if (existing) return existing;
  if (authPromise) return authPromise;
  authPromise = postAgentToken({ agent_type: "buyer", agent_id: "BA-001" })
    .then((data) => {
      storeToken(data.access_token);
      return data.access_token;
    })
    .finally(() => {
      authPromise = null;
    });
  return authPromise;
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
        Authorization: `Bearer ${t}`,
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

export async function postAutorunAbort(
  sessionId: string
): Promise<AutorunAbortResponse> {
  const res = await authFetch("/api/agent/buyer/autorun/abort", {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId }),
  });
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}`);
  }
  return res.json();
}

export async function pollAutorun(
  sessionId: string
): Promise<AutorunPollResponse> {
  const res = await authFetch(
    `/api/agent/buyer/autorun/${sessionId}`,
    { method: "GET" }
  );
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}`);
  }
  return res.json();
}
