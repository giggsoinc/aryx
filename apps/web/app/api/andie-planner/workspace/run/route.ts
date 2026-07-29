import { NextRequest, NextResponse } from "next/server";

// See app/api/andie-planner/run/route.ts for why this bypasses the generic
// rewrite — workspace-scope generation spans every dataset in the workspace,
// so it's the slowest call in the app (measured ~38s against a 21-dataset
// workspace) and the first to reliably exceed the rewrite proxy's timeout.
//
// C09's bounded repair retry can double this to two sequential LLM calls
// per request (measured: one call alone took 70s on this stack's local
// CPU-inference model) — 240s covers two slow calls with real margin.
const TARGET = process.env.ARYX_API_URL_INTERNAL || "http://api:8000";
const TIMEOUT_MS = 240_000;

export async function POST(req: NextRequest) {
  const { search } = new URL(req.url);
  const body = await req.text();
  try {
    const upstream = await fetch(`${TARGET}/andie-planner/workspace/run${search}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
    const text = await upstream.text();
    return new NextResponse(text, {
      status: upstream.status,
      headers: { "Content-Type": upstream.headers.get("Content-Type") ?? "application/json" },
    });
  } catch (e) {
    const message = e instanceof Error ? e.message : String(e);
    return NextResponse.json({
      status: "controlled_error", spec: null, error_code: "proxy_timeout",
      error_message: `Request to Andie timed out or failed in transit: ${message}`,
      attempts: 0, validation: null, analysis_datasets: [],
      created_at: new Date().toISOString(),
    });
  }
}
