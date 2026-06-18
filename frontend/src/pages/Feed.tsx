import { useCallback, useEffect, useState } from "react";
import {
  fetchArticles,
  fetchSources,
  fetchStats,
  fetchTopics,
  type ArticleQuery,
} from "../api/client";
import type { Article, Score, Source, Stats, Topic } from "../types";
import ScoreCard from "../components/ScoreCard";
import StatsHeader from "../components/StatsHeader";
import FilterBar from "../components/FilterBar";
import ArticleDetail from "../components/ArticleDetail";
import TierBadge from "../components/TierBadge";

const PAGE_SIZE = 50;

function formatDate(s: string | null): string {
  if (!s) return "—";
  const d = new Date(s);
  return isNaN(d.getTime())
    ? "—"
    : d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

/** Compact at-a-glance signals from the score: red flags raised and how many
 * other sources corroborated the same event. Both already ride along in the
 * row payload; this surfaces them without opening the detail drawer. */
function Signals({ score }: { score: Score }) {
  const flags = score.red_flags?.length ?? 0;
  const corr = score.corroboration?.distinct_sources ?? 0;
  if (!flags && !corr) return null;
  return (
    <span className="flex items-center gap-2 text-xs">
      {flags > 0 && (
        <span
          className="inline-flex items-center gap-0.5 font-medium text-red-600"
          title={`${flags} red flag${flags > 1 ? "s" : ""} raised`}
        >
          ⚑ {flags}
        </span>
      )}
      {corr > 0 && (
        <span
          className="inline-flex items-center gap-0.5 font-medium text-sky-600"
          title={`Corroborated by ${corr} other source${corr > 1 ? "s" : ""}`}
        >
          ✓ {corr}
        </span>
      )}
    </span>
  );
}

export default function Feed() {
  const [sources, setSources] = useState<Source[]>([]);
  const [topics, setTopics] = useState<Topic[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [articles, setArticles] = useState<Article[]>([]);
  const [query, setQuery] = useState<ArticleQuery>({ order: "recent" });
  const [page, setPage] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<number | null>(null);

  useEffect(() => {
    fetchSources().then(setSources).catch(() => {});
    fetchTopics().then(setTopics).catch(() => {});
    fetchStats().then(setStats).catch(() => {});
  }, []);

  const load = useCallback(() => {
    setLoading(true);
    fetchArticles({ ...query, limit: PAGE_SIZE, offset: page * PAGE_SIZE })
      .then((a) => {
        setArticles(a);
        setError(null);
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [query, page]);

  useEffect(() => load(), [load]);

  const patchQuery = (patch: Partial<ArticleQuery>) => {
    setPage(0);
    setQuery((q) => ({ ...q, ...patch }));
  };

  return (
    <div className="flex flex-col gap-5">
      <StatsHeader stats={stats} />

      <div className="flex items-center justify-between">
        <FilterBar sources={sources} topics={topics} query={query} onChange={patchQuery} />
        <button
          onClick={() => {
            fetchStats().then(setStats).catch(() => {});
            load();
          }}
          className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm hover:bg-slate-50"
        >
          Refresh
        </button>
      </div>

      {error && <p className="text-red-600">Failed to reach API: {error}</p>}

      <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
        {/* table-fixed + per-column widths so the table always fits its container
            (Title absorbs the slack and truncates); overflow-x-auto is a safety net
            so a narrow window scrolls instead of clipping the right-most column. */}
        <table className="w-full table-fixed border-collapse text-sm">
          <thead>
            <tr className="border-b border-slate-200 bg-slate-50 text-left text-slate-500">
              <th className="px-4 py-2 font-medium">Title</th>
              <th className="w-52 px-4 py-2 font-medium">Source</th>
              <th className="w-28 px-4 py-2 font-medium">Published</th>
              <th className="w-32 px-4 py-2 font-medium">Topic</th>
              <th className="w-48 px-4 py-2 font-medium">Credibility</th>
            </tr>
          </thead>
          <tbody>
            {articles.map((a) => (
              <tr
                key={a.id}
                onClick={() => setSelected(a.id)}
                className="cursor-pointer border-b border-slate-100 last:border-0 hover:bg-slate-50"
              >
                <td className="truncate px-4 py-2.5 text-slate-800">
                  {a.title ?? a.url}
                </td>
                <td className="px-4 py-2.5 text-slate-500">
                  <div className="flex items-center gap-2">
                    <span className="min-w-0 truncate">{a.source_name ?? "—"}</span>
                    {a.source_tier && (
                      <span className="shrink-0">
                        <TierBadge tier={a.source_tier} />
                      </span>
                    )}
                  </div>
                </td>
                <td className="whitespace-nowrap px-4 py-2.5 text-slate-500">
                  {formatDate(a.published_at)}
                </td>
                <td className="px-4 py-2.5">
                  {a.latest_score?.topic ? (
                    <span className="rounded bg-slate-100 px-2 py-0.5 text-xs capitalize text-slate-600">
                      {a.latest_score.topic}
                    </span>
                  ) : (
                    <span className="text-slate-300">—</span>
                  )}
                </td>
                <td className="px-4 py-2.5">
                  <div className="flex items-center gap-2.5">
                    <ScoreCard score={a.latest_score} />
                    {a.latest_score && <Signals score={a.latest_score} />}
                  </div>
                </td>
              </tr>
            ))}
            {!loading && articles.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-slate-400">
                  No articles match these filters.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between text-sm text-slate-500">
        <span>{loading ? "Loading…" : `Page ${page + 1}`}</span>
        <div className="flex gap-2">
          <button
            disabled={page === 0}
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            className="rounded-md border border-slate-300 bg-white px-3 py-1 disabled:opacity-40"
          >
            Prev
          </button>
          <button
            disabled={articles.length < PAGE_SIZE}
            onClick={() => setPage((p) => p + 1)}
            className="rounded-md border border-slate-300 bg-white px-3 py-1 disabled:opacity-40"
          >
            Next
          </button>
        </div>
      </div>

      {selected !== null && (
        <ArticleDetail articleId={selected} onClose={() => setSelected(null)} />
      )}
    </div>
  );
}
