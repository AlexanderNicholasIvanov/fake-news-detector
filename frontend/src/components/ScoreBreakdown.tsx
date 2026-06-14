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
  const corr = score.corroboration;
  return (
    <div className="flex flex-col gap-2">
      <Bar label="Final" value={score.final_score} accent={finalAccent} />
      <Bar label="Content" value={score.content_subscore} accent="bg-slate-400" />
      <Bar label="Reputation" value={score.reputation_subscore} accent="bg-slate-400" />
      {score.corroboration_subscore != null ? (
        <Bar label="Corroboration" value={score.corroboration_subscore} accent="bg-sky-500" />
      ) : (
        <div className="flex items-center gap-3">
          <span className="w-24 shrink-0 text-xs uppercase tracking-wide text-slate-500">
            Corroboration
          </span>
          <span className="text-xs italic text-slate-400">
            no matching coverage found
          </span>
        </div>
      )}
      {corr && corr.matched.length > 0 && (
        <div className="mt-1 rounded-md bg-sky-50 p-2 text-xs text-slate-600">
          <span className="font-medium text-sky-700">
            Same event reported by {corr.distinct_sources}{" "}
            {corr.distinct_sources === 1 ? "other source" : "other sources"}
            {corr.any_trusted ? " (incl. a trusted outlet)" : ""}:
          </span>
          <ul className="mt-1 list-disc space-y-0.5 pl-4">
            {corr.matched.map((m) => (
              <li key={m.article_id}>
                <span className="font-medium">{m.source_name}</span>
                {m.title ? ` — ${m.title}` : ""}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
