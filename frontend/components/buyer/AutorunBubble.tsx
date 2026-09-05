"use client";

import type { AutorunEvent } from "@/lib/buyerApi";

interface AutorunBubbleProps {
  event: AutorunEvent;
  isStreaming?: boolean;
}

const TYPE_ICONS: Record<string, string> = {
  llm: "psychology",
  tool: "build",
  governance: "shield",
  payment: "lock",
  done: "check_circle",
  aborted: "cancel",
};

const TYPE_COLORS: Record<string, { border: string; icon: string; badge: string; badgeIcon: string }> = {
  llm: { border: "border-l-emerald-400", icon: "text-emerald-600", badge: "bg-amber-50 text-amber-700 border border-amber-200", badgeIcon: "text-amber-600" },
  tool: { border: "border-l-blue-400", icon: "text-blue-600", badge: "bg-blue-50 text-blue-700 border border-blue-200", badgeIcon: "text-blue-600" },
  governance: { border: "border-l-emerald-500", icon: "text-emerald-600", badge: "bg-emerald-50 text-emerald-700 border border-emerald-200", badgeIcon: "text-emerald-600" },
  payment: { border: "border-l-emerald-500", icon: "text-emerald-600", badge: "bg-emerald-50 text-emerald-700 border border-emerald-200", badgeIcon: "text-emerald-600" },
  done: { border: "border-emerald-500", icon: "text-white", badge: "", badgeIcon: "" },
  aborted: { border: "border-l-red-400", icon: "text-red-600", badge: "", badgeIcon: "" },
};

const FAILED_COLORS = {
  border: "border-l-red-400",
  icon: "text-red-600",
  badge: "bg-red-50 text-red-700 border border-red-200",
  badgeIcon: "text-red-600",
};

const REVIEW_COLORS = {
  border: "border-l-amber-400",
  icon: "text-amber-600",
  badge: "bg-amber-50 text-amber-700 border border-amber-200",
  badgeIcon: "text-amber-600",
};

function formatEventTime(event: AutorunEvent): string {
  return event.time_ist ?? "";
}

export function AutorunBubble({ event, isStreaming }: AutorunBubbleProps) {
  const isBlocked = event.decision === "DENY" || event.decision === "FAILED";
  const isReview = event.decision === "REVIEW";
  const isFailedStatus = event.status === "failed" && !isBlocked && !isReview;
  const isDone = event.type === "done";
  const isAborted = event.type === "aborted";
  const colors =
    isBlocked || (isDone && isBlocked) || isFailedStatus
      ? FAILED_COLORS
      : isReview
        ? REVIEW_COLORS
        : TYPE_COLORS[event.type] ?? TYPE_COLORS.llm;
  const icon = TYPE_ICONS[event.type] ?? "circle";
  const failedCard =
    (isDone && isBlocked) ||
    (event.type === "payment" && isFailedStatus) ||
    (event.type === "payment_verified" && isFailedStatus) ||
    (event.type === "governance" && isBlocked);

  if (isDone) {
    return (
      <div
        className={`rounded-2xl p-4 shadow-sm border-2 ${
          isBlocked ? "bg-red-50 border-red-400" : isReview ? "bg-amber-50 border-amber-300" : "bg-emerald-50 border-emerald-400"
        }`}
      >
        <div className="flex items-center gap-2 mb-2">
          <div
            className={`w-7 h-7 rounded-full flex items-center justify-center ${
              isBlocked ? "bg-red-600" : isReview ? "bg-amber-500" : "bg-emerald-600"
            }`}
          >
            <span className="material-symbols-outlined text-sm text-white" style={{ fontVariationSettings: '"FILL" 1' }}>
              {isBlocked ? "block" : isReview ? "hourglass_empty" : icon}
            </span>
          </div>
          <span
            className={`font-headline-sm text-body-lg font-bold ${
              isBlocked ? "text-red-900" : isReview ? "text-amber-900" : "text-emerald-900"
            }`}
          >
            Buyer AI Agent
          </span>
          <span
            className={`ml-auto font-mono-label text-mono-label text-xs ${
              isBlocked ? "text-red-600" : isReview ? "text-amber-600" : "text-emerald-600"
            }`}
          >
            {formatEventTime(event)}
          </span>
        </div>
        <p
          className={`font-body-lg text-body-lg leading-relaxed ${
            isBlocked ? "text-red-900" : isReview ? "text-amber-900" : "text-emerald-900"
          }`}
        >
          {event.text}
        </p>
      </div>
    );
  }

  if (isAborted) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-2xl p-4 shadow-sm">
        <div className="flex items-center gap-2 mb-2">
          <div className="w-7 h-7 rounded-full bg-red-100 flex items-center justify-center">
            <span className={`material-symbols-outlined text-sm ${colors.icon}`} style={{ fontVariationSettings: '"FILL" 1' }}>
              {icon}
            </span>
          </div>
          <span className="font-headline-sm text-body-lg font-bold text-red-900">
            Run Stopped
          </span>
          <span className="ml-auto font-mono-label text-mono-label text-red-600 text-xs">
            {formatEventTime(event)}
          </span>
        </div>
        <p className="font-body-lg text-body-lg text-red-800 leading-relaxed">
          {event.text}
        </p>
      </div>
    );
  }

  return (
    <div
      className={`flex flex-col gap-2 pl-3 border-l-4 rounded-r-2xl pr-3 py-2 ${
        failedCard ? "bg-red-50/60 border-red-400" : colors.border
      }`}
    >
      <div className="flex items-center gap-2">
        <div className={`w-7 h-7 rounded-full ${failedCard ? "bg-red-100" : isStreaming ? "bg-emerald-100" : "bg-surface-container-high"} flex items-center justify-center`}>
          <span className={`material-symbols-outlined text-sm ${failedCard ? "text-red-600" : colors.icon}`} style={{ fontVariationSettings: '"FILL" 1' }}>
            {failedCard ? (event.type === "governance" ? "gavel" : "credit_card_off") : icon}
          </span>
        </div>
        <span className="font-headline-sm text-body-lg font-semibold text-on-surface">
          Buyer AI Agent
        </span>
        <span className={`ml-auto flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full ${failedCard ? "bg-red-100 text-red-700 border border-red-200" : colors.badge}`}>
          <span className={`material-symbols-outlined text-xs ${failedCard ? "text-red-600" : colors.badgeIcon} ${isStreaming ? "animate-pulse" : ""}`} style={{ fontVariationSettings: '"FILL" 1' }}>
            {isStreaming ? "pending" : failedCard ? "block" : "check_circle"}
          </span>
          {isStreaming ? "Running" : failedCard ? "Blocked" : "Complete"}
        </span>
        <span className="font-mono-label text-mono-label text-secondary text-xs">
          {formatEventTime(event)}
        </span>
      </div>

      <p className="font-body-lg text-body-lg text-on-surface leading-relaxed pl-9">
        {event.text}
      </p>

      {event.type === "tool" && event.products && event.products.length > 0 && (
        <div className="pl-9 mt-1">
          <div className="bg-surface-container-low rounded-xl p-3 border border-surface-container-high">
            {event.products.map((product, i) => (
              <div key={i} className="flex items-start gap-2">
                <span className="material-symbols-outlined text-emerald-600 text-base mt-0.5">shopping_bag</span>
                <div>
                  <p className="font-body-sm text-body-sm font-semibold text-on-surface">{product.name}</p>
                  <p className="font-body-sm text-body-sm text-secondary">{product.description}</p>
                  <p className="font-mono-label text-mono-label text-emerald-600 text-xs mt-0.5">{product.availability_label}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {event.quote && (
        <div className="pl-9 mt-1">
          <div className="inline-flex items-center gap-1 bg-emerald-50 border border-emerald-200 rounded-full px-3 py-1">
            <span className="material-symbols-outlined text-emerald-600 text-xs" style={{ fontVariationSettings: '"FILL" 1' }}>description</span>
            <span className="font-mono-label text-mono-label text-emerald-700 text-xs font-semibold">
              {event.quote.quote_id} — {event.quote.status_label}
            </span>
          </div>
        </div>
      )}

      {event.type === "governance" && event.decision && (
        <div className="pl-9 mt-1">
          <div
            className={`inline-flex items-center gap-1 rounded-full px-3 py-1 ${
              event.decision === "DENY" || event.decision === "FAILED"
                ? "bg-red-100 border border-red-300"
                : event.decision === "REVIEW"
                  ? "bg-amber-100 border border-amber-300"
                  : "bg-emerald-100 border border-emerald-300"
            }`}
          >
            <span
              className={`material-symbols-outlined text-xs ${
                event.decision === "DENY" || event.decision === "FAILED"
                  ? "text-red-700"
                  : event.decision === "REVIEW"
                    ? "text-amber-700"
                    : "text-emerald-700"
              }`}
              style={{ fontVariationSettings: '"FILL" 1' }}
            >
              {event.decision === "DENY" || event.decision === "FAILED" ? "gavel" : "shield"}
            </span>
            <span
              className={`font-mono-label text-mono-label text-xs font-bold ${
                event.decision === "DENY" || event.decision === "FAILED"
                  ? "text-red-800"
                  : event.decision === "REVIEW"
                    ? "text-amber-800"
                    : "text-emerald-800"
              }`}
            >
              {event.decision === "FAILED" ? "PAYMENT FAILED" : event.decision}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
