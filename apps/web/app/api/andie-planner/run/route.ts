import { NextRequest, NextResponse } from "next/server";

// Bypasses the generic /api/:path* rewrite in next.config.mjs on purpose.
// Next's built-in rewrite proxy times out well under a minute; Andie's LLM
// call (real Ollama generation) can legitimately take 10-60s+, especially as
// approved resources grow, so the generic proxy resets the socket mid-request
// (visible as "Failed to proxy ... socket hang up" in the web container log)
// before FastAPI ever gets to respond. A dedicated route with an explicit,
// generous timeout avoids that entirely. Filesystem routes take precedence
// over rewrites() by default, so only this exact path is affected.
//
// C09 (pre-execution validation) can trigger a SECOND full LLM call in the
// same request — one bounded repair retry when the first candidate is
// rejected — so this is no longer "one LLM call" but potentially two,
// sequentially. Measured against the local Ollama model in this stack: a
// single call alone took 70s (7.5 tok/s, CPU inference); two in sequence can
// exceed 120s easily. 240s covers two slow calls plus C10's (fast,
// in-process) preprocessing with real margin.
const TARGET = process.env.ARYX_API_URL_INTERNAL || "http://api:8000";
const TIMEOUT_MS = 240_000;

export async function POST(req: NextRequest) {
  const { search } = new URL(req.url);
  const body = await req.text();
  try {
    const upstream = await fetch(`${TARGET}/andie-planner/run${search}`, {
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
    // Same PlannerResult shape the backend itself returns on failure, so the
    // frontend's normal result view renders this cleanly instead of a raw error.
    return NextResponse.json({
      status: "controlled_error", spec: null, error_code: "proxy_timeout",
      error_message: `Request to Andie timed out or failed in transit: ${message}`,
      attempts: 0, validation: null, analysis_datasets: [],
      created_at: new Date().toISOString(),
    });
  }
}
