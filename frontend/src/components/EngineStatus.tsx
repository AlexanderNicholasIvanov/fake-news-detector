import { useEffect, useState } from "react";
import { fetchScoringStatus } from "../api/client";
import type { ScoringStatus } from "../types";

// Live health of the scoring engine (Ollama). When it's offline, new articles
// silently stop being scored while the rest of the app keeps working — so make
// that visible instead of silent. Self-polls every 30s; failures are swallowed
// (treated as "no data yet" rather than crashing the header).
const POLL_MS = 30_000;

export default function EngineStatus() {
  const [status, setStatus] = useState<ScoringStatus | null>(null);

  useEffect(() => {
    let active = true;
    const tick = () =>
      fetchScoringStatus()
        .then((s) => active && setStatus(s))
        .catch(() => {});
    tick();
    const id = setInterval(tick, POLL_MS);
    return () => {
      active = false;
      clearInterval(id);
    };
  }, []);

  if (!status) return null;

  const online = status.engine === "online";
  const modelsReady = status.scoring_model_ready && status.embedding_model_ready;
  const ok = online && modelsReady;

  const dot = ok ? "bg-green-500" : online ? "bg-amber-500" : "bg-red-500";
  const label = !online
    ? "Scoring engine offline"
    : !modelsReady
      ? "Models missing"
      : "Scoring engine online";

  const title = !online
    ? "Ollama is not reachable — new articles won't be scored until it's running."
    : !status.scoring_model_ready
      ? `Scoring model '${status.scoring_model}' not pulled (run: ollama pull ${status.scoring_model})`
      : !status.embedding_model_ready
        ? `Embedding model '${status.embedding_model}' not pulled (run: ollama pull ${status.embedding_model})`
        : `Ollama online — ${status.scoring_model} + ${status.embedding_model} ready`;

  return (
    <div
      className="flex items-center gap-2 rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs text-slate-600"
      title={title}
    >
      <span className={`h-2 w-2 rounded-full ${dot} ${ok ? "" : "animate-pulse"}`} />
      <span className="whitespace-nowrap">{label}</span>
    </div>
  );
}
