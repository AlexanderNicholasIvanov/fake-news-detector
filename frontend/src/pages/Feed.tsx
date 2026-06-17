import { useCallback, useEffect, useState } from "react";
import {
  fetchArticles,
  fetchSources,
  fetchStats,
  fetchTopics,
  type ArticleQuery,
} from "../api/client";
import type { Article, Source, Stats, Topic } from "../types";
import ScoreCard from "../components/ScoreCard";
import StatsHeader from "../components/StatsHeader";
import FilterBar from "../components/FilterBar";
import ArticleDetail from "../components/ArticleDetail";

const PAGE_SIZE = 50;

function formatDate(s: string | null): string {
  if (!s) return "—";
  const d = new Date(s);
  return isNaN(d.getTime())
    ? "—"
    : d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
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

      <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b border-slate-200 bg-slate-50 text-left text-slate-500">
              <th className="px-4 py-2 font-medium">Title</th>
              <th className="px-4 py-2 font-medium">Source</th>
              <th className="px-4 py-2 font-medium">Published</th>
              <th className="px-4 py-2 font-medium">Topic</th>
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
                  <ScoreCard score={a.latest_score} />
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
