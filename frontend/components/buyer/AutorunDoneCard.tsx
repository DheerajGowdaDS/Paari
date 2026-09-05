"use client";

import Link from "next/link";

interface AutorunDoneCardProps {
  txnId: string;
  quoteId: string;
  text: string;
  decision?: "ALLOW" | "REVIEW" | "DENY" | "FAILED";
}

const isBlocked = (decision?: string) =>
  decision === "DENY" || decision === "FAILED" || decision === "REVIEW";

export function AutorunDoneCard({
  txnId,
  quoteId,
  text,
  decision,
}: AutorunDoneCardProps) {
  const blocked = isBlocked(decision);

  return (
    <div
      className={`rounded-2xl p-4 shadow-sm border-2 ${
        blocked
          ? "bg-red-50 border-red-300"
          : "bg-emerald-50 border-emerald-300"
      }`}
    >
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <div
            className={`w-8 h-8 rounded-full flex items-center justify-center ${
              blocked ? "bg-red-600" : "bg-emerald-600"
            }`}
          >
            <span
              className={`material-symbols-outlined text-white text-base ${
                blocked ? "" : "text-white"
              }`}
              style={{ fontVariationSettings: '"FILL" 1' }}
            >
              {blocked ? "block" : "check_circle"}
            </span>
          </div>
          <div>
            <p
              className={`font-headline-sm text-body-lg font-bold ${
                blocked ? "text-red-900" : "text-emerald-900"
              }`}
            >
              {blocked
                ? decision === "REVIEW"
                  ? "Review Required"
                  : "Autonomous Procurement Blocked"
                : "Autonomous Procurement Complete"}
            </p>
            <p
              className={`font-body-sm text-body-sm ${
                blocked ? "text-red-700" : "text-emerald-700"
              }`}
            >
              {text}
            </p>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2 mb-3">
        <div
          className={`bg-white/70 rounded-xl p-2.5 border ${
            blocked ? "border-red-200" : "border-emerald-200"
          }`}
        >
          <p
            className={`font-mono-label text-mono-label text-[10px] uppercase tracking-wider mb-0.5 ${
              blocked ? "text-red-600" : "text-emerald-600"
            }`}
          >
            Quote
          </p>
          <p
            className={`font-mono-label text-mono-label font-semibold text-sm ${
              blocked ? "text-red-900" : "text-emerald-900"
            }`}
          >
            {quoteId}
          </p>
          <p
            className={`text-[10px] mt-0.5 ${
              blocked ? "text-red-600" : "text-emerald-600"
            }`}
          >
            {blocked ? "Not escrowed" : "Escrow queued"}
          </p>
        </div>
        <div
          className={`bg-white/70 rounded-xl p-2.5 border ${
            blocked ? "border-red-200" : "border-emerald-200"
          }`}
        >
          <p
            className={`font-mono-label text-mono-label text-[10px] uppercase tracking-wider mb-0.5 ${
              blocked ? "text-red-600" : "text-emerald-600"
            }`}
          >
            Transaction
          </p>
          <p
            className={`font-mono-label text-mono-label font-semibold text-sm ${
              blocked ? "text-red-900" : "text-emerald-900"
            }`}
          >
            {txnId}
          </p>
          <p
            className={`text-[10px] mt-0.5 ${
              blocked ? "text-red-600" : "text-emerald-600"
            }`}
          >
            {blocked ? "No payment made" : "Payment pending"}
          </p>
        </div>
      </div>

      <div className="flex items-center gap-2">
        <Link
          href="/audit"
          className={`flex-1 inline-flex items-center justify-center gap-1.5 text-white font-body-sm text-body-sm font-semibold px-4 py-2 rounded-full transition-all ${
            blocked
              ? "bg-red-600 hover:bg-red-700"
              : "bg-emerald-600 hover:bg-emerald-700"
          } active:scale-[0.98]`}
        >
          <span className="material-symbols-outlined text-base leading-none">receipt_long</span>
          {blocked ? "View Audit Trail" : "View in Audit"}
        </Link>
        <button
          className={`flex-1 inline-flex items-center justify-center gap-1.5 font-body-sm text-body-sm font-semibold px-4 py-2 rounded-full transition-all active:scale-[0.98] ${
            blocked
              ? "bg-white hover:bg-red-50 text-red-700 border border-red-300"
              : "bg-white hover:bg-emerald-50 text-emerald-700 border border-emerald-300"
          }`}
          type="button"
        >
          <span className="material-symbols-outlined text-base leading-none">description</span>
          View Full Terms
        </button>
      </div>
    </div>
  );
}
