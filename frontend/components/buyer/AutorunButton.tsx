"use client";

interface AutorunButtonProps {
  onClick: () => void;
  disabled?: boolean;
}

export function AutorunButton({ onClick, disabled }: AutorunButtonProps) {
  return (
    <div className="flex flex-col items-center gap-4 mb-6">
      <p className="font-body-md text-body-md text-secondary max-w-md text-center">
        Fully autonomous procurement. I&apos;ll search, quote, negotiate, and escrow
        — all in one click.
      </p>
      <button
        className="inline-flex items-center gap-2 bg-emerald-600 hover:bg-emerald-700 active:scale-[0.98] text-white font-body-md text-body-md font-semibold px-6 py-3 rounded-full shadow-md transition-all disabled:opacity-50 disabled:cursor-not-allowed"
        onClick={onClick}
        disabled={disabled}
        type="button"
      >
        <span className="material-symbols-outlined text-xl leading-none">
          play_arrow
        </span>
        Run Autonomous Scenario
      </button>
      <p className="font-mono-label text-mono-label text-secondary text-xs">
        ~7 seconds · auto-escrow enabled
      </p>
    </div>
  );
}
