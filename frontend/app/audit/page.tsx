"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import {
  getStoredToken,
  storeToken,
  postMerchantToken,
  getTransactions,
  getAuditDetail,
  type TransactionSummary,
  type AuditDetail,
  type TransactionStep,
} from "@/lib/merchantApi";
import { formatISOTime12hIST } from "@/lib/utils";

const LOGO_URL =
  "https://lh3.googleusercontent.com/aida/AEtjO1V1hMa6JlEw507615UgeX6HLIGHdLGAVwZtuEzaqYF_CY7OF5iKop9RDLiWgJF2CsASwHY9lZ6sly3zk7Hxo6jBi_Ai6raCwOq2gwCye_pu5wNEb-ZBJ7exThiWBhv7nyViBZfM4DLc5lLHkctS8hNMfivZhmfyAMHPj2C5hLT9hLbgOfu4vDs66nilRUnzP3Edjl1u-WpA1hQrQWMbudRBEw0koISKTuRXFHkBmUqxU-Qml04g1RBMhZLZkhqYJFLzUikvPdwA_Q";

const STEP_ICON_MAP: Record<string, string> = {
  user_request: "person",
  buyer_agent: "smart_toy",
  a2a_negotiation: "handshake",
  merchant_agent: "storefront",
  quote_accepted: "description",
  payment_request: "credit_card",
  governance: "shield",
  payment_provider: "/",
  payment_verified: "verified",
  fulfillment: "package_2",
};

function decisionTone(decision: string): { chip: string; text: string; label: string } {
  const d = (decision ?? "").toUpperCase();
  if (d === "DENY" || d === "DENIED") {
    return {
      chip: "bg-red-50 border border-red-200",
      text: "text-red-700",
      label: "Decision: DENY",
    };
  }
  if (d === "REVIEW") {
    return {
      chip: "bg-amber-50 border border-amber-200",
      text: "text-amber-700",
      label: "Decision: REVIEW",
    };
  }
  if (d === "FAILED" || d === "PAYMENT_FAILED") {
    return {
      chip: "bg-orange-50 border border-orange-200",
      text: "text-orange-700",
      label: "Decision: PAYMENT FAILED",
    };
  }
  return {
    chip: "bg-emerald-50 border border-emerald-200",
    text: "text-emerald-800",
    label: "Decision: ALLOW",
  };
}

function getStepVariant(type: string, status: string): "default" | "governance" | "razorpay" | "verified" | "success" | "failed" {
  if (status === "failed") return "failed";
  if (type === "governance") return "governance";
  if (type === "payment_provider") return "razorpay";
  if (type === "payment_verified") return "verified";
  if (type === "fulfillment" && status === "passed") return "success";
  return "default";
}

function circleClasses(variant: string): string {
  switch (variant) {
    case "governance":
      return "w-8 h-8 rounded-full bg-emerald-50 border border-emerald-300 flex items-center justify-center flex-shrink-0 text-emerald-700 z-10 shadow-sm";
    case "success":
      return "w-8 h-8 rounded-full bg-emerald-600 text-white flex items-center justify-center flex-shrink-0 z-10 shadow-sm";
    case "failed":
      return "w-8 h-8 rounded-full bg-red-50 border border-red-300 flex items-center justify-center flex-shrink-0 text-red-600 z-10 shadow-sm";
    case "razorpay":
      return "w-8 h-8 rounded-full bg-[#f4f3f0] border border-[#e7e5e4] flex items-center justify-center flex-shrink-0 text-blue-600 z-10 shadow-sm";
    case "verified":
      return "w-8 h-8 rounded-full bg-[#f4f3f0] border border-[#e7e5e4] flex items-center justify-center flex-shrink-0 text-emerald-600 z-10 shadow-sm";
    default:
      return "w-8 h-8 rounded-full bg-[#f4f3f0] border border-[#e7e5e4] flex items-center justify-center flex-shrink-0 text-[#57534e] z-10 shadow-sm";
  }
}

function titleClasses(variant: string): string {
  switch (variant) {
    case "governance":
      return "font-headline-sm text-headline-sm text-emerald-900";
    case "success":
      return "font-headline-sm text-headline-sm text-emerald-950 font-bold";
    case "failed":
      return "font-headline-sm text-headline-sm text-red-700 font-bold";
    default:
      return "font-headline-sm text-headline-sm text-on-surface";
  }
}

function StepIcon({ step }: { step: TransactionStep }) {
  if (step.type === "payment_provider") {
    return <span className="font-mono font-bold text-[13px] italic">/</span>;
  }
  return (
    <span className="material-symbols-outlined text-[15px]">{STEP_ICON_MAP[step.type] || "circle"}</span>
  );
}

function TimelineRow({ step, index, isLast }: { step: TransactionStep; index: number; isLast: boolean }) {
  const variant = getStepVariant(step.type, step.status);
  const showPaymentSuccess = step.type === "fulfillment" && step.payment_status === "success";

  return (
    <li className="relative flex items-start gap-space-md">
      {!isLast && (
        <div className="absolute left-[15px] top-10 -bottom-space-md w-[1px] bg-outline-variant z-0"></div>
      )}
      <span className="font-mono-metric text-mono-metric text-secondary w-7 pt-2 z-10 bg-background text-center">
        {String(index + 1).padStart(2, "0")}
      </span>
      <div className={circleClasses(variant)}>
        <StepIcon step={step} />
      </div>
      <div className="flex-1 bg-surface-container-lowest border border-surface-container-high rounded-2xl p-space-md shadow-sm mb-space-md">
        <div className="flex flex-wrap items-center justify-between gap-2 mb-1">
          <span className={titleClasses(variant)}>{step.title}</span>
          <span className="font-mono-metric text-mono-metric text-secondary">
            {formatISOTime12hIST(step.timestamp)}
          </span>
        </div>
        <p className="font-body-sm text-body-sm text-on-surface-variant leading-relaxed">
          {step.desc || step.description}
        </p>
        {step.decision && (
          <div className={`mt-2 inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full ${decisionTone(step.decision).chip}`}>
            <span
              className={`material-symbols-outlined ${decisionTone(step.decision).text} text-[13px]`}
              style={{ fontVariationSettings: '"FILL" 1' }}
            >
              gavel
            </span>
            <span className={`font-mono-label text-mono-label ${decisionTone(step.decision).text} font-semibold uppercase tracking-wider`}>
              {decisionTone(step.decision).label}
            </span>
          </div>
        )}
        {showPaymentSuccess && (
          <div className="mt-2 pt-2 border-t border-emerald-200 flex items-center justify-between">
            <span className="font-mono-label text-mono-label text-emerald-700 font-bold uppercase tracking-wider">
              Payment successful
            </span>
            <span
              className="material-symbols-outlined text-emerald-700 text-[15px]"
              style={{ fontVariationSettings: '"FILL" 1' }}
            >
              check_circle
            </span>
          </div>
        )}
      </div>
    </li>
  );
}

function fmtPaise(paise: number | null | undefined, currency?: string): string {
  const c = currency ?? "INR";
  const n = (paise ?? 0) / 100;
  return `${c === "INR" ? "₹" : c + " "}${n.toLocaleString("en-IN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

function stateTone(state: string): { dot: string; label: string; tile: string } {
  const s = (state ?? "").toUpperCase();
  if (s === "COMPLETED" || s === "ORDER_CONFIRMED" || s === "PAYMENT_VERIFIED") {
    return { dot: "bg-emerald-600", label: "SUCCESS", tile: "text-emerald-700" };
  }
  if (s === "DENIED" || s === "FAILED" || s === "REJECTED" || s === "PAYMENT_FAILED") {
    return { dot: "bg-red-600", label: "FAILED", tile: "text-red-600" };
  }
  if (s === "REVIEW_REQUIRED") {
    return { dot: "bg-amber-500", label: "REVIEW", tile: "text-amber-600" };
  }
  return { dot: "bg-amber-500", label: "IN PROGRESS", tile: "text-amber-600" };
}

export default function AuditPage() {
  const [isLoading, setIsLoading] = useState(true);
  const [authError, setAuthError] = useState<string | null>(null);
  const [txList, setTxList] = useState<TransactionSummary[]>([]);
  const [pinnedId, setPinnedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<AuditDetail | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [tick, setTick] = useState<number>(0);

  // Poll the real transaction list every 4s. The effective selection is the
  // newest transaction unless the user pinned an older one.
  useEffect(() => {
    let cancelled = false;
    async function refresh() {
      try {
        const list = await getTransactions();
        if (cancelled) return;
        setTxList(list);
        setAuthError(null);
      } catch {
        if (!cancelled) setAuthError("Failed to load transactions.");
      } finally {
        if (!cancelled) {
          setIsLoading(false);
          setTick((t) => t + 1);
        }
      }
    }
    refresh();
    const iv = setInterval(refresh, 4000);
    return () => {
      cancelled = true;
      clearInterval(iv);
    };
  }, []);

  // Get a token up front (authFetch handles it lazily too).
  useEffect(() => {
    let cancelled = false;
    async function ensureAuth() {
      try {
        let token = getStoredToken();
        if (!token) {
          const data = await postMerchantToken();
          token = data.access_token;
          storeToken(token);
        }
        if (!cancelled) setAuthError(null);
      } catch {
        if (!cancelled) setAuthError("Failed to load audit data.");
      }
    }
    ensureAuth();
    return () => {
      cancelled = true;
    };
  }, []);

  const newestTxnId = txList[0]?.txn_id ?? null;
  // Follow the newest transaction unless a pinned (older) one is selected.
  const selectedId = pinnedId ?? newestTxnId;

  // Fetch the audit detail whenever selection or a list tick changes.
  useEffect(() => {
    if (!selectedId) return;
    let cancelled = false;
    async function load() {
      try {
        // Clear any stale detail from a previously selected transaction so the
        // ledger never shows one tx's steps under another tx's header.
        setDetail((prev) => (prev && prev.txn_id !== selectedId ? null : prev));
        setDetailError(null);
        const d = await getAuditDetail(selectedId);
        if (cancelled) return;
        setDetail(d);
      } catch {
        if (!cancelled) setDetailError("Failed to load audit detail.");
      }
    }
    load();
    const iv = setInterval(load, 4000);
    return () => {
      cancelled = true;
      clearInterval(iv);
    };
  }, [selectedId, tick]);

  const pick = useCallback((id: string) => {
    setPinnedId((prev) => (prev === id ? null : id)); // unpin by re-clicking
  }, []);

  const selectedRow = txList.find((t) => t.txn_id === selectedId) ?? txList[0];

  if (isLoading) {
    return (
      <div className="w-full min-h-screen bg-background flex items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <div className="w-8 h-8 rounded-full border-2 border-emerald-600 border-t-transparent animate-spin"></div>
          <span className="font-mono-label text-mono-label text-secondary">Loading audit trail...</span>
        </div>
      </div>
    );
  }

  if (authError && txList.length === 0) {
    return (
      <div className="w-full min-h-screen bg-background flex items-center justify-center">
        <div className="text-center">
          <p className="text-on-surface mb-4">{authError}</p>
          <button
            onClick={() => window.location.reload()}
            className="px-4 py-2 bg-[#1c1917] text-white rounded-lg text-xs"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  const txnId = detail?.txn_id ?? selectedRow?.txn_id ?? "---";
  const firstStep = detail?.steps[0];
  const lastStep = detail?.steps[(detail?.steps?.length ?? 1) - 1];
  const passedSteps =
    detail?.checkpoints?.total
      ? detail.checkpoints.passed
      : detail?.steps.filter((s) => s.status === "passed" || s.status === "active").length ?? 0;
  const totalSteps =
    detail?.checkpoints?.total ?? detail?.steps?.length ?? 0;
  const statusNote = detail?.status_note ?? (detail?.status === "success" ? "Fulfilled" : detail?.status === "failed" ? "Failed" : "In progress");
  const decision = detail?.decision ?? (detail?.state === "DENIED" ? "DENY" : "ALLOW");
  const dTone = decisionTone(decision);
  const stateT = stateTone(detail?.state ?? selectedRow?.state ?? "");
  const displayAmount = detail?.amount_paise ?? selectedRow?.amount_paise;
  const currency = detail?.currency ?? selectedRow?.currency ?? "INR";

  return (
    <div className="w-full min-h-screen bg-background text-on-surface font-body-md text-body-md antialiased">
      <header className="fixed top-0 inset-x-0 z-50 bg-surface/85 backdrop-blur-xl border-b border-surface-container-high">
        <div className="h-16 max-w-max-width mx-auto px-gutter-mobile lg:px-gutter-desktop flex items-center justify-between gap-space-md">
          <div className="flex items-center gap-space-md">
            <Link href="/">
              <img
                alt="Paari Logo"
                className="rounded-full object-cover border border-surface-container-high shadow-sm shrink-0"
                style={{ width: 34, height: 34 }}
                src={LOGO_URL}
              />
            </Link>
            <Link
              href="/"
              className="font-headline-sm text-headline-sm text-on-surface tracking-tight font-semibold whitespace-nowrap"
            >
              Paari
            </Link>
            <span className="text-outline-variant">/</span>
            <div className="inline-flex items-center gap-space-xs bg-surface-container-low px-space-sm py-space-2xs rounded-full border border-surface-container-high">
              <span className="font-mono-label text-mono-label uppercase text-on-surface-variant tracking-wider">
                Audit Trail
              </span>
              <span className="text-outline-variant">•</span>
              <span className="font-mono-label text-mono-label text-secondary">
                Ledger
              </span>
            </div>
          </div>

          <nav className="hidden md:flex items-center gap-space-lg">
            <Link
              href="/"
              className="font-mono-label text-mono-label text-secondary hover:text-on-surface transition-colors tracking-wider"
            >
              Home
            </Link>
            <Link
              href="/buyer"
              className="font-mono-label text-mono-label text-secondary hover:text-on-surface transition-colors tracking-wider"
            >
              Buyer AI
            </Link>
            <Link
              href="/merchant"
              className="font-mono-label text-mono-label text-secondary hover:text-on-surface transition-colors tracking-wider"
            >
              Merchant
            </Link>
          </nav>
        </div>
      </header>

      <main className="w-full pt-16 min-h-screen bg-background">
        <div className="w-full max-w-[1000px] mx-auto px-gutter-mobile lg:px-gutter-desktop py-space-xl lg:py-space-2xl">
          <section className="mb-space-xl">
            <div className="font-mono-label text-mono-label uppercase tracking-wider text-secondary mb-space-xs">
              Live Ledger
            </div>
            <h1 className="font-headline-xl text-headline-xl text-on-surface tracking-tight mb-space-md">
              Full Audit Trail
            </h1>
            <p className="font-body-lg text-body-lg text-secondary max-w-2xl leading-relaxed">
              Every governance checkpoint per transaction, recorded immutably and
              verified end to end. Select any recent transaction below to inspect
              its ledger.
            </p>
          </section>

          {/* Recent transactions picker (real data) */}
          <section className="mb-space-xl">
            <div className="flex items-center justify-between mb-space-sm">
              <div className="font-mono-label text-mono-label text-secondary uppercase tracking-wider">
                Recent transactions
              </div>
              <div className="inline-flex items-center gap-1.5 font-mono-label text-mono-label text-emerald-700">
                <span className="w-2 h-2 rounded-full bg-emerald-600 animate-pulse"></span>
                LIVE
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              {txList.map((t) => {
                const active = t.txn_id === txnId;
                const tone = stateTone(t.state);
                return (
                  <button
                    key={t.txn_id + t.id}
                    onClick={() => pick(t.txn_id)}
                    className={`inline-flex items-center gap-2 px-3 py-2 rounded-full border font-mono-label text-mono-label transition-colors ${
                      active
                        ? "bg-[#1c1917] text-white border-[#1c1917]"
                        : "bg-surface-container-lowest text-on-surface-variant border-surface-container-high hover:border-[#a8a29e]"
                    }`}
                  >
                    <span className={`w-1.5 h-1.5 rounded-full ${tone.dot}`}></span>
                    <span>{t.txn_id}</span>
                    <span className={active ? "text-white/70" : "text-secondary"}>
                      {fmtPaise(t.amount_paise, t.currency)}
                    </span>
                    {t.created_at && (
                      <span className={active ? "text-white/50" : "text-outline"}>
                        {formatISOTime12hIST(t.created_at)}
                      </span>
                    )}
                  </button>
                );
              })}
              {txList.length === 0 && (
                <span className="font-body-sm text-body-sm text-secondary">
                  No transactions yet. Run a scenario from the Buyer AI console.
                </span>
              )}
            </div>
          </section>

          {/* Ledger facts */}
          <section className="mb-space-md">
            <div className="font-mono-label text-mono-label uppercase tracking-wider text-secondary mb-space-sm">
              {txnId} · Complete Ledger
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
              <div className="bg-surface-container-lowest border border-surface-container-high rounded-2xl p-space-md shadow-sm">
                <div className="font-mono-label text-mono-label text-secondary uppercase tracking-wider mb-1">
                  Decision
                </div>
                <div className={`font-headline-md text-headline-md font-semibold ${dTone.text}`}>
                  {decision}
                </div>
                <div className="font-body-sm text-body-sm text-secondary mt-0.5">{statusNote}</div>
              </div>
              <div className="bg-surface-container-lowest border border-surface-container-high rounded-2xl p-space-md shadow-sm">
                <div className="font-mono-label text-mono-label text-secondary uppercase tracking-wider mb-1">
                  Checkpoints
                </div>
                <div className="font-headline-md text-headline-md text-on-surface font-semibold">
                  {passedSteps}/{totalSteps}
                </div>
                <div className="font-body-sm text-body-sm text-secondary mt-0.5">Passed</div>
              </div>
              <div className="bg-surface-container-lowest border border-surface-container-high rounded-2xl p-space-md shadow-sm">
                <div className="font-mono-label text-mono-label text-secondary uppercase tracking-wider mb-1">
                  Amount
                </div>
                <div className="font-headline-md text-headline-md text-on-surface font-semibold">
                  {fmtPaise(displayAmount, currency)}
                </div>
                <div className="font-body-sm text-body-sm text-secondary mt-0.5 truncate max-w-[160px]">
                  {detail?.quote_id ? `Quote ${detail.quote_id.slice(0, 8)}` : selectedRow?.quote_id ?? "---"}
                </div>
              </div>
              <div className="bg-surface-container-lowest border border-surface-container-high rounded-2xl p-space-md shadow-sm">
                <div className="font-mono-label text-mono-label text-secondary uppercase tracking-wider mb-1">
                  Duration
                </div>
                <div className="font-headline-md text-headline-md text-on-surface font-semibold">
                  {detail?.duration_seconds ?? 0}s
                </div>
                <div className="font-body-sm text-body-sm text-secondary mt-0.5">
                  {firstStep ? `${formatISOTime12hIST(firstStep.timestamp)} → ${formatISOTime12hIST(lastStep?.timestamp ?? firstStep.timestamp)}` : "---"}
                </div>
              </div>
            </div>
          </section>

          {/* PSP facts */}
          {(detail?.razorpay_order_id || detail?.razorpay_payment_id || detail?.state) && (
            <section className="mb-space-xl">
              <div className="flex flex-wrap items-center gap-2">
                {detail?.state && (
                  <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-surface-container-low border border-surface-container-high font-mono-label text-mono-label text-on-surface-variant`}>
                    <span className={`w-1.5 h-1.5 rounded-full ${stateT.dot}`}></span>
                    STATE {detail.state}
                  </span>
                )}
                {detail?.razorpay_order_id && (
                  <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-[#f4f3f0] border border-[#e7e5e4] font-mono-label text-mono-label text-blue-700">
                    order {detail.razorpay_order_id}
                  </span>
                )}
                {detail?.razorpay_payment_id && (
                  <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-[#f4f3f0] border border-[#e7e5e4] font-mono-label text-mono-label text-blue-700">
                    payment {detail.razorpay_payment_id}
                  </span>
                )}
                {detailError && (
                  <span className="font-body-sm text-body-sm text-red-600">{detailError}</span>
                )}
              </div>
            </section>
          )}

          <ol className="relative">
            {detail?.steps.length ? (
              detail.steps.map((step, i) => (
                <TimelineRow
                  key={step.seq}
                  step={step}
                  index={i}
                  isLast={i === (detail.steps?.length ?? 0) - 1}
                />
              ))
            ) : (
              <li className="font-body-sm text-body-sm text-secondary py-4">
                {detailError ?? "No ledger entries for this transaction yet."}
              </li>
            )}
          </ol>

          {/* Why this transaction did not complete — real reason from the audit trail */}
          {detail?.reason && detail.status !== "success" && (
            <section className="mt-space-md mb-space-xl">
              <div
                className={`rounded-2xl border p-space-md flex items-start gap-space-md ${
                  detail.status === "failed"
                    ? "bg-red-50 border-red-200"
                    : "bg-amber-50 border-amber-200"
                }`}
              >
                <span
                  className={`material-symbols-outlined mt-0.5 ${
                    detail.status === "failed" ? "text-red-600" : "text-amber-600"
                  }`}
                >
                  {detail.status === "failed" ? "error" : "pending"}
                </span>
                <div>
                  <div
                    className={`font-mono-label text-mono-label uppercase tracking-wider mb-1 ${
                      detail.status === "failed" ? "text-red-700" : "text-amber-700"
                    }`}
                  >
                    {detail.status === "failed" ? "Why this was not fulfilled" : "Why this is not complete yet"}
                  </div>
                  <p
                    className={`font-body-md text-body-md leading-relaxed ${
                      detail.status === "failed" ? "text-red-900" : "text-amber-900"
                    }`}
                  >
                    {detail.reason}
                  </p>
                  {(detail.failed_checks?.length || detail.review_checks?.length) ? (
                    <div className="flex flex-wrap gap-2 mt-2">
                      {detail.failed_checks?.map((c) => (
                        <span
                          key={c}
                          className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-red-100 border border-red-300 font-mono-label text-mono-label text-red-800"
                        >
                          <span className="material-symbols-outlined text-[12px]">close</span>
                          {c}
                        </span>
                      ))}
                      {detail.review_checks?.map((c) => (
                        <span
                          key={c}
                          className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-amber-100 border border-amber-300 font-mono-label text-mono-label text-amber-800"
                        >
                          <span className="material-symbols-outlined text-[12px]">gavel</span>
                          {c}
                        </span>
                      ))}
                    </div>
                  ) : null}
                </div>
              </div>
            </section>
          )}

          <div className="mt-space-2xl flex flex-col sm:flex-row items-center justify-between gap-space-md bg-surface-container/50 px-space-md py-space-sm rounded-DEFAULT">
            <div className="flex items-center gap-space-xs font-mono-label text-mono-label text-on-surface-variant">
              <span className={`w-2 h-2 rounded-full ${stateT.dot}`}></span>
              <span className="">LEDGER IMMUTABLE · SIGNED &amp; SEALED</span>
            </div>
            <div className="font-mono-metric text-mono-metric text-on-surface-variant">
              {detail?.digest ?? (txnId !== "---" ? "0x...pending" : "---")}
            </div>
          </div>
        </div>
      </main>

      <footer className="border-t border-[#e7e5e4] bg-[#ffffff] px-6 py-2.5 flex items-center justify-between text-[11px] text-[#78716c]">
        <div className="">© 2026 Paari Agentic Commerce. All rights reserved.</div>
        <div className="font-mono text-[#a8a29e]">v1.0.0</div>
      </footer>
    </div>
  );
}
