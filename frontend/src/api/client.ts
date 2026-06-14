import type { Article } from "../types";

// Requests go to /api/* and are proxied to the backend by Vite (see vite.config.ts).
export async function fetchArticles(limit = 50, offset = 0): Promise<Article[]> {
  const res = await fetch(`/api/articles?limit=${limit}&offset=${offset}`);
  if (!res.ok) throw new Error(`GET /api/articles failed: ${res.status}`);
  return res.json();
}
