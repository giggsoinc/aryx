import type { AskResponse, Workspace } from "./types";

const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8088";

/** Throw on non-2xx; return parsed JSON otherwise. */
async function fetchJSON<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
    ...init,
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}: ${detail}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  listWorkspaces: () =>
    fetchJSON<Workspace[]>("/admin/workspaces?workspace_id=1"),

  ask: (question: string, workspaceId: number, history: unknown[] = []) =>
    fetchJSON<AskResponse>("/ask", {
      method: "POST",
      body: JSON.stringify({ question, workspace_id: workspaceId, history }),
    }),
};
