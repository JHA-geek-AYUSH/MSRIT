import { NextResponse } from "next/server";

/**
 * DEPRECATED — this was a copy-pasted stub from the FragFest AgentOS project:
 * it returned randomly-templated fake "task complete" text from an in-memory
 * array with no real LLM call, and reset on every server restart.
 *
 * The real agentic environment for this project is the FastAPI backend's
 * 7-tool FinTriage agent — see:
 *   backend/app/agents/fintriage_agent.py
 *   backend/app/api/v1/agent.py           (POST /v1/agent)
 *   frontend/lib/compliance-api.ts        (runAgent(), runAssessment())
 *   frontend/app/agent/page.tsx           (real Agent Console UI)
 *
 * This route intentionally now returns 410 Gone instead of fake data.
 */
export async function GET() {
  return NextResponse.json(
    { error: "This mock endpoint has been retired. Use POST /v1/agent on the FastAPI backend instead." },
    { status: 410 }
  );
}

export async function POST() {
  return NextResponse.json(
    { error: "This mock endpoint has been retired. Use POST /v1/agent on the FastAPI backend instead." },
    { status: 410 }
  );
}
