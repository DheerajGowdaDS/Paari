/* eslint-disable @next/next/no-img-element */
"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import {
  getStoredToken,
  storeToken,
  postMerchantToken,
  getTransactionsCurrent,
  getConnection,
  getConnections,
  type Transaction,
  type Connection,
  type TransactionStep,
} from "@/lib/merchantApi";
import { formatTimeIST } from "@/lib/utils";

const DOVE_URL =
  "https://lh3.googleusercontent.com/aida-public/AB6AXuC0KQvxkBGHjGxVfgP_oL26v11f6P-YGrbhl0cEq5IXJ78OVH7h199F9pVr8U0LgGt1wHbdfIWN2Id9aN01FqSKULfDlVYI_CbsRqoSBFS82pOK_vfcwNReX7PxjAmCcXTV9E9aJA4GLsuS1QmMbUHenZgmLT1yzw4xwsFKGnUqjM0bdwGlJ1IlAO-2TyvuA2sIRBcKsAP-pLbvVEMsFT2RgSNwADZhVO4d1L0YX3vJwUcorgx_30GSO_gctcGr4mA66A";

const STEP_TO_NODE: Record<number, string> = {
  1: "buyer_agent",
  2: "buyer_agent",
  3: "merchant_agent",
  4: "merchant_agent",
  5: "paari_gateway",
  6: "paari_gateway",
  7: "paari_gateway",
  8: "payment_gateway",
  9: "razorpay",
  10: "shopify",
};

function stepCircleClasses(status: string, variant?: string): string {
  if (status === "failed") return "w-7 h-7 rounded-full bg-red-50 border-2 border-red-400 flex items-center justify-center flex-shrink-0 text-red-600 z-10 shadow-xs";
  if (status === "active") return "w-7 h-7 rounded-full bg-emerald-100 border-2 border-emerald-500 flex items-center justify-center flex-shrink-0 text-emerald-600 z-10 shadow-sm animate-pulse";
  if (variant === "governance") return "w-7 h-7 rounded-full bg-emerald-50 border border-emerald-300 flex items-center justify-center flex-shrink-0 text-emerald-700 z-10 shadow-xs";
  if (variant === "razorpay") return "w-7 h-7 rounded-full bg-[#f4f3f0] border border-[#e7e5e4] flex items-center justify-center flex-shrink-0 text-blue-600 z-10 shadow-xs";
  if (variant === "verified" || status === "passed") return "w-7 h-7 rounded-full bg-emerald-600 text-white flex items-center justify-center flex-shrink-0 z-10 shadow-xs";
  return "w-7 h-7 rounded-full bg-[#f4f3f0] border border-[#e7e5e4] flex items-center justify-center flex-shrink-0 text-[#57534e] z-10 shadow-xs";
}

function stepCardClasses(status: string, variant?: string): string {
  if (status === "failed") return "flex-1 bg-red-50/60 border border-red-300 rounded-xl p-2.5";
  if (status === "active") return "flex-1 bg-emerald-50 border-2 border-emerald-400 rounded-xl p-2.5 shadow-md";
  if (variant === "governance") return "flex-1 bg-emerald-50/40 border border-emerald-200/80 rounded-xl p-2.5";
  if (variant === "success") return "flex-1 bg-emerald-50/60 border border-emerald-300 rounded-xl p-2.5 shadow-xs";
  return "flex-1 bg-[#faf9f7] border border-[#e7e5e4] rounded-xl p-2.5 hover:border-[#d6d3d1] transition";
}

function stepTitleClasses(status: string, variant?: string): string {
  if (status === "failed") return "font-bold text-red-700";
  if (status === "active") return "font-bold text-emerald-800";
  if (variant === "governance") return "font-semibold text-emerald-900";
  if (variant === "success") return "font-bold text-emerald-950";
  return "font-semibold text-[#1c1917]";
}

function decisionTextClasses(decision?: string): string {
  const d = (decision ?? "").toUpperCase();
  if (d === "DENY" || d === "DENIED") return "text-red-600";
  if (d === "REVIEW") return "text-amber-600";
  if (d === "FAILED" || d === "PAYMENT_FAILED") return "text-orange-600";
  return "text-emerald-700";
}

function statusTone(status?: string): { badge: string; dot: string; label: string; txId: string } {
  if (status === "failed") {
    return {
      badge: "bg-red-50 text-red-700 border border-red-200",
      dot: "bg-red-600",
      label: "FAILED",
      txId: "text-red-700",
    };
  }
  if (status === "in_progress") {
    return {
      badge: "bg-amber-50 text-amber-700 border border-amber-200",
      dot: "bg-amber-500",
      label: "IN PROGRESS",
      txId: "text-amber-700",
    };
  }
  return {
    badge: "bg-emerald-50 text-emerald-700 border border-emerald-200",
    dot: "bg-emerald-600",
    label: "LIVE",
    txId: "text-emerald-700",
  };
}

function StepIcon({ step }: { step: TransactionStep }) {
  if (step.type === "payment_provider" || step.provider === "razorpay") {
    return <span className="font-mono font-bold text-[12px] italic">/</span>;
  }
  const iconMap: Record<string, string> = {
    user_request: "person",
    buyer_agent: "smart_toy",
    a2a_negotiation: "handshake",
    merchant_agent: "storefront",
    quote_accepted: "description",
    payment_request: "credit_card",
    governance: "shield",
    payment_verified: "verified",
    fulfillment: "package_2",
  };
  return <span className="material-symbols-outlined text-[14px]">{iconMap[step.type] || "circle"}</span>;
}

function StepRow({ step, isLast }: { step: TransactionStep; isLast: boolean }) {
  return (
    <div className="relative flex items-start space-x-2.5">
      {!isLast && (
        <div className={`absolute left-[13.5px] top-7 -bottom-2.5 w-[1px] z-0 ${step.status === "passed" ? "bg-emerald-400" : step.status === "failed" ? "bg-red-400" : "bg-[#e7e5e4]"}`}></div>
      )}
      <div className={stepCircleClasses(step.status, step.type)}>
        <StepIcon step={step} />
      </div>
      <div className={stepCardClasses(step.status, step.type)}>
        <div className="flex items-center justify-between mb-0.5">
          <span className={stepTitleClasses(step.status, step.type)}>{step.title}</span>
          <span className="text-[10px] text-[#78716c] font-mono">{step.time}</span>
        </div>
        <p className="text-[11px] text-[#57534e] leading-snug">{step.desc || step.description}</p>
        {step.decision && (
          <p className={`text-[11px] font-semibold mt-0.5 ${decisionTextClasses(step.decision)}`}>
            Decision: {step.decision}
          </p>
        )}
        {step.status === "passed" ? (
          <div className="flex justify-end mt-1">
            <span className="material-symbols-outlined text-emerald-600 text-[14px]" style={{ fontVariationSettings: '"FILL" 1' }}>check_circle</span>
          </div>
        ) : step.status === "failed" ? (
          <div className="flex justify-end mt-1">
            <span className="material-symbols-outlined text-red-600 text-[14px]" style={{ fontVariationSettings: '"FILL" 1' }}>cancel</span>
          </div>
        ) : step.status === "active" ? (
          <div className="flex justify-end mt-1">
            <span className="material-symbols-outlined text-emerald-600 text-[14px] animate-pulse" style={{ fontVariationSettings: '"FILL" 1' }}>pending</span>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function NodeCard({ name, icon, isActive, onClick }: { name: string; icon: string; isActive: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={`py-2.5 px-3 bg-[#faf9f7] border rounded-xl flex items-center justify-center space-x-2 shadow-xs transition-all flex-1 min-w-0 ${isActive ? "border-emerald-500 shadow-emerald-200 animate-pulse" : "border-emerald-500/50 hover:border-emerald-600"}`}
    >
      <span className="material-symbols-outlined text-emerald-700 text-[20px]">{icon}</span>
      <span className="text-xs font-semibold text-[#1c1917]">{name}</span>
    </button>
  );
}

function ConnectionSummaryCard({ connection, onClick }: { connection: Connection; onClick: () => void }) {
  const iconMap: Record<string, string> = {
    shopify: "shopping_bag",
    razorpay: "/",
    a2a: "hub",
    llm: "psychology",
    buyer_agent: "smart_toy",
    merchant_agent: "storefront",
    paari_gateway: "shield",
    payment_gateway: "lock",
  };

  return (
    <button
      onClick={onClick}
      className="bg-[#faf9f7] border border-[#e7e5e4] rounded-xl p-2.5 flex items-center justify-between hover:border-[#d6d3d1] transition cursor-pointer shadow-xs w-full text-left"
    >
      <div className="flex items-center space-x-2.5">
        <div className={`w-8 h-8 rounded-lg ${connection.status === "connected" || connection.status === "operational" ? "bg-emerald-50 border border-emerald-200" : "bg-[#f4f3f0] border border-[#e7e5e4]"} flex items-center justify-center text-[#1c1917]`}>
          <span className="material-symbols-outlined text-[16px]">{iconMap[connection.id] || "circle"}</span>
        </div>
        <div>
          <div className="flex items-center space-x-1.5">
            <span className="font-semibold text-[#1c1917] text-xs">{connection.name}</span>
            <span className={`text-[9px] font-bold ${connection.status === "connected" || connection.status === "operational" ? "text-emerald-700 bg-emerald-100/70" : "text-[#78716c] bg-[#f4f3f0]"} px-1.5 py-0.2 rounded uppercase`}>
              {connection.status}
            </span>
          </div>
          <div className="text-[10px] text-[#78716c] mt-0.5">{connection.mode || connection.details?.model || connection.details?.provider || ""}</div>
        </div>
      </div>
      <span className="material-symbols-outlined text-[15px] text-[#78716c]">chevron_right</span>
    </button>
  );
}

function ConnectionDetail({ connection, onBack }: { connection: Connection; onBack: () => void }) {
  const iconMap: Record<string, string> = {
    shopify: "shopping_bag",
    razorpay: "/",
    a2a: "hub",
    llm: "psychology",
    buyer_agent: "smart_toy",
    merchant_agent: "storefront",
    paari_gateway: "shield",
    payment_gateway: "lock",
  };

  const details = connection.details;
  const detailRows: Array<{ label: string; value: string | number }> = [];

  // Payment Gateway node: dedicated bounded-payment panel (real transaction data)
  if (connection.id === "payment_gateway" && details.transaction_id) {
    return (
      <div className="bg-[#ffffff] border border-[#e7e5e4] rounded-2xl p-4 shadow-sm flex-1 overflow-y-auto">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center space-x-2">
            <div className="w-8 h-8 rounded-lg bg-emerald-50 border border-emerald-200 flex items-center justify-center">
              <span className="material-symbols-outlined text-emerald-700 text-[18px]">lock</span>
            </div>
            <h2 className="text-sm font-semibold text-[#1c1917]">{connection.name}</h2>
          </div>
          <button onClick={onBack} className="text-xs text-emerald-700 hover:text-emerald-800 font-medium flex items-center space-x-1">
            <span className="material-symbols-outlined text-[14px]">arrow_back</span>
            <span>Back</span>
          </button>
        </div>

        <p className="text-[11px] text-[#78716c] mb-3 leading-relaxed">
          Paari does not give the agent unrestricted payment access. It issues a
          bounded payment session and a one-time payment capability tied to this
          transaction.
        </p>

        {details.session_bound ? (
          <div className="space-y-2.5">
            {/* Authorized amount — the hero number */}
            <div className="bg-[#faf9f7] border border-[#e7e5e4] rounded-xl p-3">
              <div className="text-[10px] text-[#78716c] font-medium uppercase tracking-wide">Authorized Amount</div>
              <div className="text-xl font-bold text-[#1c1917] mt-0.5">
                ₹{((details.authorized_amount_paise ?? 0) / 100).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                <span className="text-[11px] font-medium text-[#78716c] ml-1.5">{details.currency || "INR"}</span>
              </div>
              <div className="text-[10px] text-[#78716c] mt-0.5">
                Bound to transaction <span className="font-mono text-[#1c1917]">{details.transaction_id}</span>
              </div>
            </div>

            {/* Payment session */}
            <div className="bg-[#faf9f7] border border-[#e7e5e4] rounded-xl p-3 space-y-1.5">
              <div className="flex items-center justify-between">
                <span className="text-[10px] text-[#78716c] font-medium uppercase tracking-wide">Payment Session</span>
                <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded uppercase ${details.session_status === "ACTIVE" ? "text-emerald-700 bg-emerald-100/70" : details.session_status === "COMPLETED" ? "text-blue-700 bg-blue-50" : "text-[#78716c] bg-[#f4f3f0]"}`}>
                  {details.session_status || "—"}
                </span>
              </div>
              <div className="flex justify-between text-[11px]">
                <span className="text-[#78716c]">Session</span>
                <span className="font-mono font-medium text-[#1c1917]">{details.session_id || "—"}</span>
              </div>
              {details.session_expires_at && (
                <div className="flex justify-between text-[11px]">
                  <span className="text-[#78716c]">Expires</span>
                  <span className="font-mono text-[#1c1917]">{formatTimeIST(new Date(details.session_expires_at))}</span>
                </div>
              )}
              {details.razorpay_order_id && (
                <div className="flex justify-between text-[11px]">
                  <span className="text-[#78716c]">Razorpay Order</span>
                  <span className="font-mono text-[#1c1917]">{details.razorpay_order_id}</span>
                </div>
              )}
            </div>

            {/* One-time capability */}
            <div className="bg-[#faf9f7] border border-[#e7e5e4] rounded-xl p-3 space-y-1.5">
              <div className="flex items-center justify-between">
                <span className="text-[10px] text-[#78716c] font-medium uppercase tracking-wide">One-Time Capability</span>
                <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded uppercase ${details.capability_used ? "text-blue-700 bg-blue-50" : "text-emerald-700 bg-emerald-100/70"}`}>
                  {details.capability_used ? "USED" : "UNUSED"}
                </span>
              </div>
              <div className="flex justify-between text-[11px]">
                <span className="text-[#78716c]">Capability</span>
                <span className="font-mono font-medium text-[#1c1917]">{details.capability_id || "—"}</span>
              </div>
              <div className="flex justify-between text-[11px]">
                <span className="text-[#78716c]">Action</span>
                <span className="font-mono text-[#1c1917]">{details.capability_action || "—"}</span>
              </div>
              <div className="flex justify-between text-[11px]">
                <span className="text-[#78716c]">Usage</span>
                <span className="font-mono text-[#1c1917]">{details.capability_usage || "—"} • used {details.capability_used ?? 0}×</span>
              </div>
              {details.capability_max_paise !== undefined && (
                <div className="flex justify-between text-[11px]">
                  <span className="text-[#78716c]">Max Amount</span>
                  <span className="font-mono text-[#1c1917]">₹{(details.capability_max_paise / 100).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                </div>
              )}
            </div>
          </div>
        ) : (
          <div className="bg-[#faf9f7] border border-[#e7e5e4] rounded-xl p-3 text-[11px] text-[#78716c]">
            No bounded payment session yet for this transaction. Paari creates a
            session and a one-time capability only after governance returns ALLOW.
          </div>
        )}

        <div className="flex items-center justify-between mt-3 pt-2.5 border-t border-[#f4f3f0] text-[10px] text-[#78716c]">
          <span>{details.sessions_active ?? 0} active / {details.sessions_bound_total ?? 0} total sessions</span>
          <span>~{details.avg_verification_time_ms ?? 0}ms verification</span>
        </div>
      </div>
    );
  }

  if (details.store_name) detailRows.push({ label: "Store", value: details.store_name });
  if (details.webhook_status) detailRows.push({ label: "Webhook", value: details.webhook_status });
  if (details.last_sync) detailRows.push({ label: "Last Sync", value: formatTimeIST(new Date(details.last_sync)) });
  if (details.orders_today !== undefined) detailRows.push({ label: "Orders Today", value: details.orders_today });
  if (details.fulfillment_rate !== undefined) detailRows.push({ label: "Fulfillment Rate", value: `${details.fulfillment_rate}%` });
  if (details.buyer_agents_online !== undefined) detailRows.push({ label: "Buyer Agents Online", value: details.buyer_agents_online });
  if (details.merchant_agents_online !== undefined) detailRows.push({ label: "Merchant Agents Online", value: details.merchant_agents_online });
  if (details.queue !== undefined) detailRows.push({ label: "Queue", value: details.queue });
  if (details.services_online !== undefined) detailRows.push({ label: "Services Online", value: `${details.services_online}/${details.services_total || ""}` });
  if (details.policies_enforced !== undefined) detailRows.push({ label: "Policies Enforced", value: details.policies_enforced });
  if (details.transactions_today !== undefined) detailRows.push({ label: "Transactions Today", value: details.transactions_today });
  if (details.avg_decision_time_ms !== undefined) detailRows.push({ label: "Avg Decision Time", value: `${details.avg_decision_time_ms}ms` });
  if (details.model) detailRows.push({ label: "Model", value: details.model });
  if (details.provider) detailRows.push({ label: "Provider", value: details.provider });
  if (details.avg_response_time_ms !== undefined) detailRows.push({ label: "Avg Response", value: `${details.avg_response_time_ms}ms` });
  if (details.error_rate !== undefined) detailRows.push({ label: "Error Rate", value: `${details.error_rate}%` });

  return (
    <div className="bg-[#ffffff] border border-[#e7e5e4] rounded-2xl p-4 shadow-sm flex-1">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center space-x-2">
          <div className="w-8 h-8 rounded-lg bg-emerald-50 border border-emerald-200 flex items-center justify-center">
            <span className="material-symbols-outlined text-emerald-700 text-[18px]">{iconMap[connection.id] || "circle"}</span>
          </div>
          <h2 className="text-sm font-semibold text-[#1c1917]">{connection.name}</h2>
        </div>
        <button onClick={onBack} className="text-xs text-emerald-700 hover:text-emerald-800 font-medium flex items-center space-x-1">
          <span className="material-symbols-outlined text-[14px]">arrow_back</span>
          <span>Back</span>
        </button>
      </div>

      <div className="mb-3">
        <span className={`text-[10px] font-bold px-2 py-0.5 rounded uppercase ${connection.status === "connected" || connection.status === "operational" || connection.status === "ok" ? "bg-emerald-100 text-emerald-700" : "bg-[#f4f3f0] text-[#78716c]"}`}>
          {connection.status}
        </span>
        {connection.mode && <span className="text-[10px] text-[#78716c] ml-2">{connection.mode}</span>}
      </div>

      <div className="space-y-2">
        {detailRows.map((row) => (
          <div key={row.label} className="flex items-center justify-between py-1 border-b border-[#f4f3f0]">
            <span className="text-[11px] text-[#78716c]">{row.label}</span>
            <span className="text-[11px] font-mono font-medium text-[#1c1917]">{row.value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function MerchantPage() {
  const [isLoading, setIsLoading] = useState(true);
  const [authError, setAuthError] = useState<string | null>(null);
  const [transaction, setTransaction] = useState<Transaction | null>(null);
  const [connections, setConnections] = useState<Connection[]>([]);
  const [selectedConnection, setSelectedConnection] = useState<Connection | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [activeNodeId, setActiveNodeId] = useState<string | null>(null);

  const fetchTransaction = useCallback(async () => {
    try {
      const data = await getTransactionsCurrent();
      setTransaction(data);
      if (data.current_step) {
        setActiveNodeId(STEP_TO_NODE[data.current_step] || null);
      }
    } catch (err) {
      console.error("Transaction fetch error:", err);
    }
  }, []);

  const fetchConnections = useCallback(async () => {
    try {
      const data = await getConnections();
      setConnections(data);
    } catch (err) {
      console.error("Connections fetch error:", err);
    }
  }, []);

  useEffect(() => {
    let txnInterval: ReturnType<typeof setInterval> | null = null;
    let connectionsInterval: ReturnType<typeof setInterval> | null = null;

    async function initAuth() {
      try {
        const existingToken = getStoredToken();
        if (!existingToken) {
          const tokenData = await postMerchantToken();
          storeToken(tokenData.access_token);
        }
        await fetchTransaction();
        await fetchConnections();
        setAuthError(null);
        txnInterval = setInterval(fetchTransaction, 3000);
        connectionsInterval = setInterval(fetchConnections, 15000);
      } catch {
        setAuthError("Failed to authenticate. Please refresh.");
      } finally {
        setIsLoading(false);
      }
    }
    initAuth();

    return () => {
      if (txnInterval) clearInterval(txnInterval);
      if (connectionsInterval) clearInterval(connectionsInterval);
    };
  }, [fetchTransaction, fetchConnections]);

  const handleNodeClick = async (nodeId: string) => {
    setSelectedConnection(null);
    setSelectedNodeId(nodeId);
    setActiveNodeId(nodeId);
    try {
      const data = await getConnection(nodeId);
      setSelectedConnection(data);
    } catch (err) {
      console.error("Connection fetch error:", err);
    }
  };

  const handleConnectionClick = (connectionId: string) => {
    handleNodeClick(connectionId);
  };

  const handleCloseDetail = () => {
    setSelectedConnection(null);
    setSelectedNodeId(null);
  };

  // Keep an open detail panel live (3s poll) so it reflects the running
  // transaction — e.g. the bounded-payment panel updates as the tx progresses.
  useEffect(() => {
    if (!selectedNodeId) return;
    const nodeId = selectedNodeId;
    const interval = setInterval(async () => {
      try {
        const data = await getConnection(nodeId);
        setSelectedConnection(data);
      } catch {
        // keep the last good panel on transient errors
      }
    }, 3000);
    return () => clearInterval(interval);
  }, [selectedNodeId]);

  if (isLoading) {
    return (
      <div className="bg-[#faf9f7] min-h-screen flex items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <div className="w-8 h-8 rounded-full border-2 border-emerald-600 border-t-transparent animate-spin"></div>
          <span className="font-mono text-[11px] text-[#78716c]">Loading...</span>
        </div>
      </div>
    );
  }

  if (authError) {
    return (
      <div className="bg-[#faf9f7] min-h-screen flex items-center justify-center">
        <div className="text-center">
          <p className="text-[#1c1917] mb-4">{authError}</p>
          <button onClick={() => window.location.reload()} className="px-4 py-2 bg-[#1c1917] text-white rounded-lg text-xs">Retry</button>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-[#faf9f7] text-[#1c1917] font-sans antialiased min-h-screen flex flex-col justify-between selection:bg-emerald-100 selection:text-emerald-900 text-xs">
      <header className="border-b border-[#e7e5e4] bg-[#ffffff]/90 backdrop-blur-md px-6 py-3 flex items-center justify-between sticky top-0 z-50">
        <div className="flex items-center space-x-3">
          <div className="flex items-center space-x-2.5">
            <div className="rounded-lg overflow-hidden flex items-center justify-center bg-[#faf9f7] border border-[#e7e5e4] shadow-sm p-0.5" style={{ width: 36, height: 36 }}>
              <img alt="Paari Dove" className="w-full h-full object-contain mix-blend-multiply transform scale-125" src={DOVE_URL} />
            </div>
            <Link href="/" className="text-base font-bold tracking-tight text-[#1c1917]">Paari</Link>
          </div>
          <div className="h-4 w-[1px] bg-[#e7e5e4] mx-1"></div>
          <div className="flex items-center space-x-2 text-[#78716c] text-xs">
            <span className="font-medium">Agentic Commerce Control Plane</span>
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-600 inline-block animate-pulse"></span>
          </div>
        </div>

        <nav className="hidden md:flex items-center space-x-4 text-xs text-[#78716c]">
          <Link href="/" className="hover:text-[#1c1917] transition-colors font-medium">Home</Link>
          <Link href="/buyer" className="hover:text-[#1c1917] transition-colors font-medium">Buyer AI</Link>
          <Link href="/audit" className="hover:text-[#1c1917] transition-colors font-medium">Audit</Link>
        </nav>

        <div className="flex items-center space-x-3.5">
          <div className="flex items-center space-x-2 bg-[#f4f3f0] border border-[#e7e5e4] px-3 py-1 rounded-full text-[11px] font-semibold text-emerald-700 shadow-sm">
            <span className="w-2 h-2 rounded-full bg-emerald-600 animate-pulse"></span>
            <span className="tracking-wide">SYSTEM ONLINE</span>
          </div>
          <div className="w-7 h-7 rounded-full bg-[#1c1917] text-white flex items-center justify-center font-mono font-semibold text-[11px] shadow-sm">PA</div>
        </div>
      </header>

      <main className="flex-1 grid grid-cols-1 lg:grid-cols-12 gap-4 p-4 max-w-[1720px] mx-auto w-full">
        {/* Column 1: Live Transaction Data Flow */}
        <section className="lg:col-span-4 xl:col-span-3 flex flex-col bg-[#ffffff] border border-[#e7e5e4] rounded-2xl overflow-hidden shadow-sm">
          <div className="p-3.5 border-b border-[#e7e5e4] bg-[#ffffff]">
            <div className="flex items-center justify-between mb-1.5">
              <h2 className="text-sm font-semibold text-[#1c1917] tracking-wide">Live Transaction Data Flow</h2>
              <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold ${statusTone(transaction?.status).badge}`}>
                <span className={`w-1.5 h-1.5 rounded-full ${statusTone(transaction?.status).dot} mr-1 animate-pulse`}></span>
                {statusTone(transaction?.status).label}
              </span>
            </div>
            <div className="flex items-center space-x-1.5 text-[#78716c] text-[11px]">
              <span className="">Transaction</span>
              <span className={`font-mono font-semibold ${statusTone(transaction?.status).txId}`}>{transaction?.txn_id || "---"}</span>
            </div>
          </div>

          <div className="p-3 flex-1 overflow-y-auto space-y-2.5 relative custom-scroll text-[11px] max-h-[820px]">
            {transaction?.steps.map((step, i) => (
              <StepRow key={step.seq} step={step} isLast={i === (transaction.steps?.length || 0) - 1} />
            )) || <p className="text-center text-[#78716c] py-8">No active transaction</p>}
          </div>

          <Link href="/audit" className="p-3 border-t border-[#e7e5e4] bg-[#faf9f7] hover:bg-[#f4f3f0] flex items-center justify-between text-[#78716c] hover:text-[#1c1917] text-xs transition group">
            <span className="flex items-center space-x-2">
              <span className="material-symbols-outlined text-[15px] text-[#78716c] group-hover:text-[#1c1917]">receipt_long</span>
              <span className="font-medium text-[#1c1917]">View full audit trail</span>
            </span>
            <span className="material-symbols-outlined text-[16px] transform group-hover:translate-x-0.5 transition">chevron_right</span>
          </Link>
        </section>

        {/* Column 2: Paari Governance Architecture */}
        <section className="lg:col-span-4 xl:col-span-6 flex flex-col bg-[#ffffff] border border-[#e7e5e4] rounded-2xl p-4 relative shadow-sm">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center space-x-2">
              <span className="material-symbols-outlined text-emerald-600 text-[18px]">account_balance</span>
              <h2 className="text-sm font-semibold text-[#1c1917] tracking-wide">Paari Governance Architecture</h2>
            </div>
          </div>

          <div className="flex-1 flex flex-col items-center justify-between relative py-2 w-full">
            <div className="w-full max-w-[500px] flex flex-col items-center relative z-10 py-1 space-y-3">
              {/* Tier 1: Agents & Shopify Row */}
              <div className="flex items-center justify-between w-full px-1 gap-2">
                <NodeCard name="AI Buyer Agent" icon="smart_toy" isActive={activeNodeId === "buyer_agent"} onClick={() => handleNodeClick("buyer_agent")} />
                <div className="flex items-center justify-center px-1 text-emerald-600 flex-shrink-0">
                  <svg fill="none" height="16" viewBox="0 0 36 16" width="36">
                    <line stroke="#059669" strokeWidth="1.5" x1="5" x2="31" y1="8" y2="8"></line>
                    <polygon fill="#059669" points="6,4 1,8 6,12"></polygon>
                    <polygon fill="#059669" points="30,4 35,8 30,12"></polygon>
                  </svg>
                </div>
                <NodeCard name="Merchant Agent" icon="storefront" isActive={activeNodeId === "merchant_agent"} onClick={() => handleNodeClick("merchant_agent")} />
                <div className="flex items-center justify-center px-1 text-emerald-600 flex-shrink-0">
                  <svg fill="none" height="16" viewBox="0 0 36 16" width="36">
                    <line stroke="#059669" strokeWidth="1.5" x1="5" x2="31" y1="8" y2="8"></line>
                    <polygon fill="#059669" points="6,4 1,8 6,12"></polygon>
                  </svg>
                </div>
                <NodeCard name="shopify" icon="shopping_bag" isActive={activeNodeId === "shopify"} onClick={() => handleNodeClick("shopify")} />
              </div>

              {/* Agents & Shopify → Gateway convergence (aligned to card centers: buyer x=66, merchant x=242; arrowhead centered between them at x=154) */}
              <div className="w-full flex justify-center -my-1">
                <svg className="block" height="26" width="500" viewBox="0 0 500 26" fill="none">
                  <path d="M 66 0 V 12 H 154 V 20" stroke="#059669" strokeWidth="1.5"></path>
                  <path d="M 242 0 V 12 H 154" stroke="#059669" strokeWidth="1.5"></path>
                  <polygon fill="#059669" points="150,19 154,25 158,19"></polygon>
                </svg>
              </div>

              {/* Paari Governance Gateway */}
              <button
                onClick={() => handleNodeClick("paari_gateway")}
                className={`w-full border-2 rounded-2xl p-3.5 bg-[#ffffff] shadow-sm transition-all ${activeNodeId === "paari_gateway" ? "border-emerald-500 shadow-emerald-200 animate-pulse" : "border-emerald-500/80 hover:border-emerald-600"}`}
              >
                <div className="flex items-center justify-center space-x-2 mb-3">
                  <div className="w-6 h-6 rounded-full bg-emerald-50 border border-emerald-200 flex items-center justify-center text-emerald-700 shadow-2xs">
                    <span className="material-symbols-outlined text-[15px]" style={{ fontVariationSettings: '"FILL" 1' }}>shield</span>
                  </div>
                  <span className="text-[13px] font-bold text-[#1c1917] tracking-tight">Paari Governance Gateway</span>
                </div>
                <div className="grid grid-cols-3 gap-2 mb-2.5">
                  <div className="bg-[#faf9f7] border border-[#e7e5e4] rounded-xl p-2.5 flex flex-col items-center justify-center text-center shadow-xs">
                    <span className="material-symbols-outlined text-emerald-700 text-[18px] mb-1">person_pin</span>
                    <span className="text-[11px] font-medium text-[#1c1917]">Identity</span>
                  </div>
                  <div className="bg-[#faf9f7] border border-[#e7e5e4] rounded-xl p-2.5 flex flex-col items-center justify-center text-center shadow-xs">
                    <span className="material-symbols-outlined text-emerald-700 text-[18px] mb-1">key</span>
                    <span className="text-[11px] font-medium text-[#1c1917]">Authorization</span>
                  </div>
                  <div className="bg-[#faf9f7] border border-[#e7e5e4] rounded-xl p-2.5 flex flex-col items-center justify-center text-center shadow-xs">
                    <span className="material-symbols-outlined text-emerald-700 text-[18px] mb-1">policy</span>
                    <span className="text-[11px] font-medium text-[#1c1917]">Policies</span>
                  </div>
                  <div className="bg-[#faf9f7] border border-[#e7e5e4] rounded-xl p-2.5 flex flex-col items-center justify-center text-center shadow-xs">
                    <span className="material-symbols-outlined text-emerald-700 text-[18px] mb-1">verified_user</span>
                    <span className="text-[11px] font-medium text-[#1c1917]">Risk</span>
                  </div>
                  <div className="bg-[#faf9f7] border border-[#e7e5e4] rounded-xl p-2.5 flex flex-col items-center justify-center text-center shadow-xs">
                    <span className="material-symbols-outlined text-emerald-700 text-[18px] mb-1">receipt_long</span>
                    <span className="text-[11px] font-medium text-[#1c1917]">Transaction</span>
                  </div>
                  <div className="bg-[#faf9f7] border border-[#e7e5e4] rounded-xl p-2.5 flex flex-col items-center justify-center text-center shadow-xs">
                    <span className="material-symbols-outlined text-emerald-700 text-[18px] mb-1">tune</span>
                    <span className="text-[11px] font-medium text-[#1c1917] leading-tight text-center">Session /<br />Capability</span>
                  </div>
                </div>
                <div className="bg-[#faf9f7] border border-[#e7e5e4] rounded-xl py-2 px-3 flex items-center justify-center space-x-2.5 shadow-xs">
                  <span className="material-symbols-outlined text-emerald-700 text-[18px]">assignment</span>
                  <div className="flex flex-col items-start">
                    <span className="text-[11px] font-bold text-[#1c1917] leading-tight">Audit</span>
                    <span className="text-[10px] text-[#78716c] font-medium">Explainable • Bounded • Auditable</span>
                  </div>
                </div>
              </button>

              {/* Gateway → Payment Gateway → {Razorpay, Shopify} — gapless flow block */}
              <div className="w-[380px] mx-auto relative -mt-1">
                {/* solid arrow: gateway → payment gateway (centered) */}
                <svg className="block" height="26" width="380" viewBox="0 0 380 26" fill="none">
                  <line x1="190" y1="0" x2="190" y2="18" stroke="#059669" strokeWidth="1.5"></line>
                  <polygon fill="#059669" points="186,17 190,23 194,17"></polygon>
                </svg>

                {/* full-width payment gateway node, aligned above both bottom nodes */}
                <button
                  onClick={() => handleNodeClick("payment_gateway")}
                  className={`w-full py-3 px-3 bg-[#faf9f7] border rounded-xl flex flex-col items-center justify-center text-center shadow-xs transition-all ${activeNodeId === "payment_gateway" ? "border-emerald-500 shadow-emerald-200 animate-pulse" : "border-emerald-500/70 hover:border-emerald-600"}`}
                >
                  <div className="flex items-center space-x-1.5">
                    <span className="material-symbols-outlined text-emerald-700 text-[16px]">lock</span>
                    <span className="text-xs font-semibold text-[#1c1917]">Payment Gateway</span>
                  </div>
                  <span className="text-[9px] text-[#78716c] font-medium mt-0.5">Session • Capability • Amount</span>
                </button>

                {/* solid arrow: payment gateway → razorpay (centered) */}
                <svg className="block" height="26" width="380" viewBox="0 0 380 26" fill="none">
                  <line x1="190" y1="0" x2="190" y2="13" stroke="#059669" strokeWidth="1.5"></line>
                  <polygon fill="#059669" points="186,12 190,18 194,12"></polygon>
                </svg>

                <button
                  onClick={() => handleNodeClick("razorpay")}
                  className={`w-full py-2.5 px-3 bg-[#faf9f7] border border-[#e7e5e4] rounded-xl flex flex-col items-center justify-center text-center shadow-xs transition-all ${activeNodeId === "razorpay" ? "border-blue-500 shadow-blue-200 animate-pulse" : "hover:border-[#d6d3d1]"}`}
                >
                  <div className="flex items-center space-x-1 mb-0.5">
                    <span className="text-blue-600 font-mono font-black text-sm italic mr-0.5">/</span>
                    <span className="text-xs font-bold text-[#1c1917] tracking-tight">Razorpay</span>
                  </div>
                  <span className="text-[10px] text-[#78716c]">Secure Payment Execution</span>
                </button>
              </div>
            </div>
          </div>
        </section>

        {/* Column 3: Connections */}
        <section className="lg:col-span-4 xl:col-span-3 flex flex-col">
          {selectedConnection ? (
            <ConnectionDetail connection={selectedConnection} onBack={handleCloseDetail} />
          ) : (
            <div className="bg-[#ffffff] border border-[#e7e5e4] rounded-2xl p-4 shadow-sm flex-1">
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-sm font-semibold text-[#1c1917] tracking-wide">Connections</h2>
                <span className="text-[10px] text-[#78716c]">Click node for details</span>
              </div>
              <div className="space-y-2.5">
                {connections.filter((c) => c.id === "shopify" || c.id === "razorpay").map((conn) => (
                  <ConnectionSummaryCard key={conn.id} connection={conn} onClick={() => handleConnectionClick(conn.id)} />
                ))}
                {connections.filter((c) => c.id === "shopify" || c.id === "razorpay").length === 0 && (
                  <p className="text-center text-[#78716c] py-4 text-[11px]">No connections found</p>
                )}
              </div>
            </div>
          )}
        </section>
      </main>

      <footer className="border-t border-[#e7e5e4] bg-[#ffffff] px-6 py-2.5 flex items-center justify-between text-[11px] text-[#78716c]">
        <div className="">© 2026 Paari Technologies. All rights reserved.</div>
        <div className="font-mono text-[#a8a29e]">v1.0.0</div>
      </footer>
    </div>
  );
}
