import type { Score } from "../types";

const BAND_STYLES: Record<Score["band"], string> = {
  credible: "bg-green-100 text-green-800 ring-green-600/20",
  questionable: "bg-amber-100 text-amber-800 ring-amber-600/20",
  misleading: "bg-red-100 text-red-800 ring-red-600/20",
};

export default function ScoreCard({ score }: { score: Score | null }) {
  if (!score) {
    return <span className="text-xs text-slate-400">unscored</span>;
  }
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset ${BAND_STYLES[score.band]}`}
      title={score.rationale ?? undefined}
    >
      <strong>{score.final_score}</strong>
      <span className="capitalize">{score.band}</span>
    </span>
  );
}
