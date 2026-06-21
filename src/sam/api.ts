// Thin typed client for the SAM backend. Paths are proxied to FastAPI in dev
// (see vite.config.ts).

import type { BillLineIn, FlowResult, StageResult } from "./types";

async function post<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body ?? {}),
  });
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json() as Promise<T>;
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json() as Promise<T>;
}

const base = (id: number) => `/api/cases/${id}`;

export const api = {
  createCase: (entry_point?: string, seed_intent?: string) =>
    post<StageResult>("/api/cases", { entry_point, seed_intent }),
  getCase: (id: number) => get<StageResult>(base(id)),
  stage0: (id: number, problem_type: string) => post<StageResult>(`${base(id)}/stage0`, { problem_type }),
  stage1: (id: number, insurance_situation: string, plan_identifier?: string) =>
    post<StageResult>(`${base(id)}/stage1`, { insurance_situation, plan_identifier }),
  stage2: (id: number, body: Record<string, unknown>) => post<StageResult>(`${base(id)}/stage2`, body),
  stage3: (id: number, lines: BillLineIn[]) => post<StageResult>(`${base(id)}/stage3`, { lines }),
  stage3alt: (id: number) => post<StageResult>(`${base(id)}/stage3alt`),
  stage4: (id: number, body: Record<string, unknown>) => post<StageResult>(`${base(id)}/stage4`, body),
  acceptCheckpoint: (id: number) => post<StageResult>(`${base(id)}/checkpoint/accept`),
  flow1: (id: number) => post<FlowResult>(`${base(id)}/flow1/explain`),
  flow2: (id: number) => post<FlowResult>(`${base(id)}/flow2/check`),
  flow3: (id: number) => post<FlowResult>(`${base(id)}/flow3/appeal`),
  handoff: (id: number, reason?: string) => post<{ status: string }>(`${base(id)}/handoff`, { reason }),
};

// cents -> "$1,240.00"
export const dollars = (cents: number | null | undefined) =>
  cents == null ? "—" : `$${(cents / 100).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
