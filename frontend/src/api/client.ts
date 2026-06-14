import type { Article, ArticleDetail, Source, Stats, Topic } from "../types";

// Requests go to /api/* and are proxied to the backend by Vite (see vite.config.ts).

export interface ArticleQuery {
  band?: string;
  topic?: string;
  source_id?: number;
  min_score?: number;
  order?: "recent" | "score_desc" | "score_asc";
  limit?: number;
  offset?: number;
}

export async function fetchArticles(q: ArticleQuery = {}): Promise<Article[]> {
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(q)) {
    if (v !== undefined && v !== "" && v !== null) params.set(k, String(v));
  }
  return getJSON(`/api/articles?${params.toString()}`);
}

export function fetchArticle(id: number): Promise<ArticleDetail> {
  return getJSON(`/api/articles/${id}`);
}

export function fetchSources(): Promise<Source[]> {
  return getJSON("/api/sources");
}

export function fetchTopics(): Promise<Topic[]> {
  return getJSON("/api/topics");
}

export function fetchStats(): Promise<Stats> {
  return getJSON("/api/stats");
}

async function getJSON<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`GET ${url} failed: ${res.status}`);
  return res.json();
}
