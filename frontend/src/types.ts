// Mirrors backend Pydantic schemas (app/schemas.py).

export interface RedFlag {
  type: string;
  severity: "low" | "medium" | "high";
  evidence: string;
}

export interface Score {
  final_score: number;
  band: "credible" | "questionable" | "misleading";
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
  published_at: string | null;
  extraction_status: string;
  latest_score: Score | null;
}
