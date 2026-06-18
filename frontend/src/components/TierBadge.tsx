// Reputation tier of a source, color-coded. Tiers come from config/reputation
// (trusted | unknown | questionable); anything unrecognized falls back to slate.

const TIER_STYLES: Record<string, string> = {
  trusted: "bg-green-100 text-green-800 ring-green-600/20",
  questionable: "bg-red-100 text-red-800 ring-red-600/20",
  unknown: "bg-slate-100 text-slate-600 ring-slate-500/20",
};

export default function TierBadge({ tier }: { tier: string }) {
  const cls = TIER_STYLES[tier] ?? TIER_STYLES.unknown;
  return (
    <span
      className={`inline-flex items-center rounded px-1.5 py-0.5 text-[11px] font-medium capitalize ring-1 ring-inset ${cls}`}
      title={`Source reputation: ${tier}`}
    >
      {tier}
    </span>
  );
}
