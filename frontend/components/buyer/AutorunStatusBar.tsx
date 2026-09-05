"use client";

interface AutorunStatusBarProps {
  currentSeq: number;
  maxSeq: number;
  currentText: string;
  type: string;
  onAbort: () => void;
}

const TYPE_STEP_LABELS: Record<string, string> = {
  llm: "AI reasoning",
  tool: "Tool execution",
  governance: "Governance check",
  payment: "Payment",
};

export function AutorunStatusBar({
  currentSeq,
  maxSeq,
  currentText,
  type,
  onAbort,
}: AutorunStatusBarProps) {
  return (
    <div className="bg-surface-container rounded-2xl p-4 border border-surface-container-high shadow-sm">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-full bg-emerald-100 flex items-center justify-center">
            <span className="material-symbols-outlined text-emerald-700 text-sm animate-pulse">
              smart_toy
            </span>
          </div>
          <span className="font-headline-sm text-body-lg font-semibold text-on-surface">
            Buyer AI — Autonomous Run
          </span>
        </div>
        <span className="inline-flex items-center gap-1 text-xs font-semibold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-200">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-600 animate-pulse"></span>
          Running
        </span>
      </div>

      <div className="flex items-center gap-2 mb-2">
        <div className="flex-1 h-1.5 bg-surface-container-high rounded-full overflow-hidden">
          <div
            className="h-full bg-emerald-500 rounded-full transition-all duration-300"
            style={{ width: `${Math.max(8, (currentSeq / maxSeq) * 100)}%` }}
          ></div>
        </div>
        <span className="font-mono-label text-mono-label text-secondary text-xs shrink-0">
          Step {currentSeq}/{maxSeq}
        </span>
      </div>

      <div className="flex items-center justify-between">
        <p className="font-body-sm text-body-sm text-secondary truncate flex-1 mr-4">
          {TYPE_STEP_LABELS[type] ?? type}: {currentText}
        </p>
        <button
          className="shrink-0 inline-flex items-center gap-1 text-xs font-medium text-secondary hover:text-error transition-colors px-2 py-1 rounded-lg hover:bg-error-container"
          onClick={onAbort}
          type="button"
        >
          <span className="material-symbols-outlined text-sm leading-none">close</span>
          Stop
        </button>
      </div>
    </div>
  );
}
