import { NextRequest, NextResponse } from "next/server";

// See app/api/andie-planner/run/route.ts for why this bypasses the generic
// rewrite — this endpoint calls the LLM too (ask-to-visualize's narrow
// draft prompt), plus draft_delta's own bounded repair retry can make that
// TWO sequential LLM calls in one request, same as the batch planner.
// Without this dedicated route, a slow/rate-limited call hits the generic
// rewrite's timeout and surfaces to the browser as a bare "500 Internal
// Server Error" even though FastAPI was still working (visible in the web
// container log as "Failed to proxy ... socket hang up").
const TARGET = process.env.ARYX_API_URL_INTERNAL || "http://api:8000";
const TIMEOUT_MS = 240_000;

export async function POST(req: NextRequest) {
  const { search } = new URL(req.url);
  const body = await req.text();
  try {
    const upstream = await fetch(`${TARGET}/andie-planner/delta/draft${search}`, {
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
    // Same DeltaDraftResult shape the backend itself returns on failure, so
    // AskToVisualizePanel renders this cleanly instead of a raw error.
    return NextResponse.json({
      status: "controlled_error", items: null, preview_text: "", would_validate: false,
      validation_errors: [], error_code: "proxy_timeout",
      error_message: `Request to Andie timed out or failed in transit: ${message}`,
      attempts: 0, created_at: new Date().toISOString(),
    });
  }
}
