import { NextRequest, NextResponse } from "next/server";

// See app/api/andie-planner/run/route.ts for why this bypasses the generic
// rewrite — confirm_delta re-validates then chains C10->C11->C12->C13->C14
// in one call (deliberately, so the chart appears immediately), so it can
// run at least as long as a full spec run even though it's touching only
// one new item.
const TARGET = process.env.ARYX_API_URL_INTERNAL || "http://api:8000";
const TIMEOUT_MS = 240_000;

export async function POST(req: NextRequest) {
  const { search } = new URL(req.url);
  const body = await req.text();
  try {
    const upstream = await fetch(`${TARGET}/andie-planner/delta/confirm${search}`, {
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
      attempts: 0, validation: null, analysis_datasets: [], execution_plans: [],
      created_at: new Date().toISOString(),
    });
  }
}
