// Mirrors backend Pydantic schemas (app/schemas.py).

export interface RedFlag {
  type: string;
  severity: "low" | "medium" | "high";
  evidence: string;
}

export type Band = "credible" | "questionable" | "misleading";

export interface Score {
  final_score: number;
  band: Band;
  reputation_subscore: number;
  content_subscore: number;
  corroboration_subscore: number | null;
  red_flags: RedFlag[];
  rationale: string | null;
  model_name: string;
  scored_at: string;
}

export interface Article {
  id: number;
  url: string;
  title: string | null;
  source_name: string | null;
  source_tier: string | null;
  published_at: string | null;
  extraction_status: string;
  latest_score: Score | null;
}

export interface ArticleDetail extends Article {
  full_text: string | null;
}

export interface Source {
  id: number;
  name: string;
  reputation_tier: string;
  article_count: number;
}

export interface Stats {
  total_articles: number;
  extracted: number;
  scored: number;
  bands: Record<string, number>;
}
