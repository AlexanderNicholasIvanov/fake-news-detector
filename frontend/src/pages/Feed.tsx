import { useCallback, useEffect, useState } from "react";
import { fetchArticles, fetchSources, fetchStats, type ArticleQuery } from "../api/client";
import type { Article, Source, Stats } from "../types";
import ScoreCard from "../components/ScoreCard";
import StatsHeader from "../components/StatsHeader";
import FilterBar from "../components/FilterBar";
import ArticleDetail from "../components/ArticleDetail";

const PAGE_SIZE = 50;

export default function Feed() {
  const [sources, setSources] = useState<Source[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [articles, setArticles] = useState<Article[]>([]);
  const [query, setQuery] = useState<ArticleQuery>({ order: "recent" });
  const [page, setPage] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<number | null>(null);

  useEffect(() => {
    fetchSources().then(setSources).catch(() => {});
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
        <FilterBar sources={sources} query={query} onChange={patchQuery} />
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

      <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b border-slate-200 bg-slate-50 text-left text-slate-500">
              <th className="px-4 py-2 font-medium">Title</th>
              <th className="px-4 py-2 font-medium">Source</th>
              <th className="px-4 py-2 font-medium">Credibility</th>
            </tr>
          </thead>
          <tbody>
            {articles.map((a) => (
              <tr
                key={a.id}
                onClick={() => setSelected(a.id)}
                className="cursor-pointer border-b border-slate-100 last:border-0 hover:bg-slate-50"
              >
                <td className="max-w-md truncate px-4 py-2.5 text-slate-800">
                  {a.title ?? a.url}
                </td>
                <td className="px-4 py-2.5 text-slate-500">{a.source_name ?? "—"}</td>
                <td className="px-4 py-2.5">
                  <ScoreCard score={a.latest_score} />
                </td>
              </tr>
            ))}
            {!loading && articles.length === 0 && (
              <tr>
                <td colSpan={3} className="px-4 py-8 text-center text-slate-400">
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
