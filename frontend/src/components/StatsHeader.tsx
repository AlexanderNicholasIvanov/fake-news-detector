import type { Stats } from "../types";

const BANDS = [
  { key: "credible", label: "Credible", color: "bg-green-500" },
  { key: "questionable", label: "Questionable", color: "bg-amber-500" },
  { key: "misleading", label: "Misleading", color: "bg-red-500" },
] as const;

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

  const unscored = Math.max(0, stats.extracted - stats.scored);
  const pct = stats.extracted ? Math.round((stats.scored / stats.extracted) * 100) : 0;
  const scored = stats.scored;

  return (
    <div className="grid gap-x-6 gap-y-4 rounded-lg border border-slate-200 bg-white px-6 py-4 md:grid-cols-[auto_1fr]">
      {/* Raw counts */}
      <div className="flex flex-wrap items-center gap-8 md:border-r md:border-slate-100 md:pr-6">
        <Stat label="Articles" value={stats.total_articles} />
        <Stat label="Extracted" value={stats.extracted} />
        <Stat label="Scored" value={stats.scored} />
        <Stat label="Unscored" value={unscored} />
      </div>

      {/* Scoring progress + credibility mix */}
      <div className="flex flex-col justify-center gap-3 md:pl-2">
        <div>
          <div className="mb-1 flex items-center justify-between text-xs text-slate-500">
            <span className="uppercase tracking-wide">Scoring progress</span>
            <span className="font-medium tabular-nums text-slate-700">
              {stats.scored.toLocaleString()} / {stats.extracted.toLocaleString()} ({pct}%)
            </span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-slate-100">
            <div
              className="h-full rounded-full bg-slate-800 transition-[width] duration-500"
              style={{ width: `${pct}%` }}
            />
          </div>
        </div>

        {scored > 0 && (
          <div>
            <div className="flex h-2 overflow-hidden rounded-full bg-slate-100">
              {BANDS.map((b) => {
                const n = stats.bands[b.key] ?? 0;
                const w = (n / scored) * 100;
                return w > 0 ? (
                  <div
                    key={b.key}
                    className={b.color}
                    style={{ width: `${w}%` }}
                    title={`${b.label}: ${n}`}
                  />
                ) : null;
              })}
            </div>
            <div className="mt-1.5 flex flex-wrap items-center gap-x-4 gap-y-1">
              {BANDS.map((b) => {
                const n = stats.bands[b.key] ?? 0;
                const w = scored ? Math.round((n / scored) * 100) : 0;
                return (
                  <div key={b.key} className="flex items-center gap-1.5 text-xs">
                    <span className={`h-2.5 w-2.5 rounded-full ${b.color}`} />
                    <span className="font-medium tabular-nums">{n}</span>
                    <span className="text-slate-500">{b.label}</span>
                    <span className="tabular-nums text-slate-400">{w}%</span>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
