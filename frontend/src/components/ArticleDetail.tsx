import { useEffect, useState } from "react";
import { fetchArticle } from "../api/client";
import type { ArticleDetail as Detail, RedFlag } from "../types";
import ScoreBreakdown from "./ScoreBreakdown";

const SEVERITY_CLS: Record<RedFlag["severity"], string> = {
  high: "bg-red-100 text-red-800",
  medium: "bg-amber-100 text-amber-800",
  low: "bg-slate-100 text-slate-700",
};

export default function ArticleDetail({
  articleId,
  onClose,
}: {
  articleId: number;
  onClose: () => void;
}) {
  const [detail, setDetail] = useState<Detail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setDetail(null);
    setError(null);
    fetchArticle(articleId).then(setDetail).catch((e) => setError(String(e)));
  }, [articleId]);

  return (
    <div
      className="fixed inset-0 z-50 flex justify-end bg-slate-900/30"
      onClick={onClose}
    >
      <div
        className="h-full w-full max-w-xl overflow-y-auto bg-white shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sticky top-0 flex items-center justify-between border-b border-slate-200 bg-white px-6 py-4">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
            Article detail
          </h2>
          <button
            onClick={onClose}
            className="rounded px-2 py-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
          >
            ✕
          </button>
        </div>

        {error && <p className="px-6 py-6 text-red-600">{error}</p>}
        {!detail && !error && <p className="px-6 py-6 text-slate-500">Loading…</p>}

        {detail && (
          <div className="flex flex-col gap-6 px-6 py-6">
            <div>
              <a
                href={detail.url}
                target="_blank"
                rel="noreferrer"
                className="text-lg font-semibold text-slate-900 hover:underline"
              >
                {detail.title ?? detail.url}
              </a>
              <p className="mt-1 text-sm text-slate-500">
                {detail.source_name}
                {detail.source_tier && (
                  <span className="ml-2 rounded bg-slate-100 px-1.5 py-0.5 text-xs capitalize">
                    {detail.source_tier}
                  </span>
                )}
                {detail.latest_score?.topic && (
                  <span className="ml-2 rounded bg-sky-50 px-1.5 py-0.5 text-xs capitalize text-sky-700">
                    {detail.latest_score.topic}
                  </span>
                )}
              </p>
            </div>

            {detail.latest_score ? (
              <>
                <ScoreBreakdown score={detail.latest_score} />

                <div>
                  <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
                    Rationale
                  </h3>
                  <p className="text-sm leading-relaxed text-slate-700">
                    {detail.latest_score.rationale}
                  </p>
                </div>

                <div>
                  <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
                    Red flags ({detail.latest_score.red_flags.length})
                  </h3>
                  {detail.latest_score.red_flags.length === 0 ? (
                    <p className="text-sm text-slate-400">None detected.</p>
                  ) : (
                    <ul className="flex flex-col gap-2">
                      {detail.latest_score.red_flags.map((f, i) => (
                        <li key={i} className="rounded-md border border-slate-200 p-3">
                          <div className="mb-1 flex items-center gap-2">
                            <span className="text-sm font-medium">
                              {f.type.replace(/_/g, " ")}
                            </span>
                            <span
                              className={`rounded px-1.5 py-0.5 text-xs font-medium ${SEVERITY_CLS[f.severity]}`}
                            >
                              {f.severity}
                            </span>
                          </div>
                          <p className="text-sm italic text-slate-600">“{f.evidence}”</p>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </>
            ) : (
              <p className="text-sm text-slate-400">Not yet scored.</p>
            )}

            {detail.full_text && (
              <div>
                <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Extracted text
                </h3>
                <p className="max-h-64 overflow-y-auto whitespace-pre-wrap text-sm leading-relaxed text-slate-600">
                  {detail.full_text.slice(0, 4000)}
                  {detail.full_text.length > 4000 ? "…" : ""}
                </p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
