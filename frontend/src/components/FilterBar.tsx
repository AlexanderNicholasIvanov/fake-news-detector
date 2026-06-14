import type { Source } from "../types";
import type { ArticleQuery } from "../api/client";

interface Props {
  sources: Source[];
  query: ArticleQuery;
  onChange: (patch: Partial<ArticleQuery>) => void;
}

const selectCls =
  "rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-sm focus:border-slate-500 focus:outline-none";

export default function FilterBar({ sources, query, onChange }: Props) {
  return (
    <div className="flex flex-wrap items-center gap-3">
      <select
        className={selectCls}
        value={query.band ?? ""}
        onChange={(e) => onChange({ band: e.target.value || undefined })}
      >
        <option value="">All bands</option>
        <option value="credible">Credible</option>
        <option value="questionable">Questionable</option>
        <option value="misleading">Misleading</option>
      </select>

      <select
        className={selectCls}
        value={query.source_id ?? ""}
        onChange={(e) =>
          onChange({ source_id: e.target.value ? Number(e.target.value) : undefined })
        }
      >
        <option value="">All sources</option>
        {sources.map((s) => (
          <option key={s.id} value={s.id}>
            {s.name} ({s.reputation_tier})
          </option>
        ))}
      </select>

      <select
        className={selectCls}
        value={query.order ?? "recent"}
        onChange={(e) => onChange({ order: e.target.value as ArticleQuery["order"] })}
      >
        <option value="recent">Most recent</option>
        <option value="score_desc">Score: high → low</option>
        <option value="score_asc">Score: low → high</option>
      </select>
    </div>
  );
}
