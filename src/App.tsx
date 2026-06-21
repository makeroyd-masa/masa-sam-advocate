import { useEffect, useState } from "react";

// Phase 0 placeholder: confirms the frontend builds and can reach the backend.
// The real universal-SAM surface (FAB, bottom-sheet, answer cards) is Phase 7.
type Health = {
  status: string;
  version: string;
  databases: Record<string, { connected: boolean; [k: string]: unknown }>;
};

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/health")
      .then((r) => r.json())
      .then(setHealth)
      .catch((e) => setError(String(e)));
  }, []);

  return (
    <main style={{ maxWidth: 640, margin: "0 auto", padding: "48px 24px" }}>
      <img src="/logo.svg" alt="MASA" style={{ width: 140, marginBottom: 24 }} />
      <h1 style={{ color: "var(--masa-horizon)" }}>SAM — Medical Bill Advocate</h1>
      <p style={{ color: "var(--masa-harbor)" }}>
        Phase 0 scaffold. Backend health below.
      </p>
      {error && <p style={{ color: "var(--masa-flare)" }}>Backend unreachable: {error}</p>}
      {health && (
        <pre
          style={{
            background: "var(--surface-card)",
            borderRadius: "var(--radius)",
            padding: 16,
            fontSize: 13,
            overflowX: "auto",
          }}
        >
          {JSON.stringify(health, null, 2)}
        </pre>
      )}
    </main>
  );
}
