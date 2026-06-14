import type { Score } from "../types";

function Bar({ label, value, accent }: { label: string; value: number; accent: string }) {
  return (
    <div className="flex items-center gap-3">
      <span className="w-24 shrink-0 text-xs uppercase tracking-wide text-slate-500">
        {label}
      </span>
      <div className="h-2 flex-1 overflow-hidden rounded-full bg-slate-100">
        <div className={`h-full ${accent}`} style={{ width: `${value}%` }} />
      </div>
      <span className="w-8 text-right text-sm font-medium tabular-nums">{value}</span>
    </div>
  );
}

export default function ScoreBreakdown({ score }: { score: Score }) {
  const finalAccent =
    score.band === "credible"
      ? "bg-green-500"
      : score.band === "questionable"
        ? "bg-amber-500"
        : "bg-red-500";
  return (
    <div className="flex flex-col gap-2">
      <Bar label="Final" value={score.final_score} accent={finalAccent} />
      <Bar label="Content" value={score.content_subscore} accent="bg-slate-400" />
      <Bar label="Reputation" value={score.reputation_subscore} accent="bg-slate-400" />
    </div>
  );
}
