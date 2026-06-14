import Feed from "./pages/Feed";

export default function App() {
  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto max-w-5xl px-6 py-4">
          <h1 className="text-lg font-semibold">Fake-News Detector</h1>
          <p className="text-sm text-slate-500">
            Credibility scores for incoming news articles
          </p>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-6 py-8">
        <Feed />
      </main>
    </div>
  );
}
