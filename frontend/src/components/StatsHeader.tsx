import type { Stats } from "../types";

const BAND_DOT: Record<string, string> = {
  credible: "bg-green-500",
  questionable: "bg-amber-500",
  misleading: "bg-red-500",
};

function Stat({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="flex flex-col">
      <span className="text-2xl font-semibold tabular-nums">{value}</span>
      <span className="text-xs uppercase tracking-wide text-slate-500">{label}</span>
    </div>
  );
}

export default function StatsHeader({ stats }: { stats: Stats | null }) {
  if (!stats) return null;
  return (
    <div className="flex flex-wrap items-center gap-8 rounded-lg border border-slate-200 bg-white px-6 py-4">
      <Stat label="Articles" value={stats.total_articles} />
      <Stat label="Extracted" value={stats.extracted} />
      <Stat label="Scored" value={stats.scored} />
      <div className="flex items-center gap-4">
        {(["credible", "questionable", "misleading"] as const).map((b) => (
          <div key={b} className="flex items-center gap-1.5 text-sm">
            <span className={`h-2.5 w-2.5 rounded-full ${BAND_DOT[b]}`} />
            <span className="tabular-nums font-medium">{stats.bands[b] ?? 0}</span>
            <span className="capitalize text-slate-500">{b}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
