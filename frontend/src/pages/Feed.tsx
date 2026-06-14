import { useEffect, useState } from "react";
import { fetchArticles } from "../api/client";
import type { Article } from "../types";
import ScoreCard from "../components/ScoreCard";

type LoadState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; articles: Article[] };

export default function Feed() {
  const [state, setState] = useState<LoadState>({ status: "loading" });

  useEffect(() => {
    fetchArticles()
      .then((articles) => setState({ status: "ready", articles }))
      .catch((err) => setState({ status: "error", message: String(err) }));
  }, []);

  if (state.status === "loading") {
    return <p className="text-slate-500">Loading…</p>;
  }
  if (state.status === "error") {
    return <p className="text-red-600">Failed to reach API: {state.message}</p>;
  }
  if (state.articles.length === 0) {
    return (
      <p className="text-slate-500">
        No articles yet. The ingestion worker (M1) will populate this feed.
      </p>
    );
  }

  return (
    <table className="w-full border-collapse text-sm">
      <thead>
        <tr className="border-b border-slate-200 text-left text-slate-500">
          <th className="py-2 pr-4 font-medium">Title</th>
          <th className="py-2 pr-4 font-medium">Source</th>
          <th className="py-2 font-medium">Credibility</th>
        </tr>
      </thead>
      <tbody>
        {state.articles.map((a) => (
          <tr key={a.id} className="border-b border-slate-100">
            <td className="py-2 pr-4">
              <a href={a.url} target="_blank" rel="noreferrer" className="text-slate-800 hover:underline">
                {a.title ?? a.url}
              </a>
            </td>
            <td className="py-2 pr-4 text-slate-500">{a.source_name ?? "—"}</td>
            <td className="py-2">
              <ScoreCard score={a.latest_score} />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
