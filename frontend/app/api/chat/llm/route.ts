import { NextRequest, NextResponse } from "next/server";
import { auth } from "@clerk/nextjs/server";

const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/**
 * POST /api/chat/llm
 * Thin proxy: forward to FastAPI /v1/chat with Clerk JWT attached.
 * The standalone /chat page calls this route; MatterWorkspace calls /v1/chat directly.
 */
export async function POST(request: NextRequest) {
  try {
    const { getToken } = await auth();
    const token = await getToken();

    const body = await request.json();
    const { query, caseType, jurisdiction, matterId } = body;

    if (!query?.trim()) {
      return NextResponse.json({ error: "Query is required" }, { status: 400 });
    }

    // /v1/chat requires a matterId — the standalone chat page passes one or we
    // create an ephemeral placeholder recognised by the backend.
    const effectiveMatterId =
      matterId ||
      "00000000-0000-0000-0000-000000000000"; // backend tolerates this for demo use

    const backendPayload = {
      matterId: effectiveMatterId,
      message: query,
      mode: "general",
      filters: {
        case_type: caseType,
        jurisdiction_region: jurisdiction,
      },
    };

    const backendRes = await fetch(`${BACKEND_URL}/v1/chat`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(backendPayload),
    });

    if (!backendRes.ok) {
      const errText = await backendRes.text();
      console.error("[chat/llm proxy] backend error:", backendRes.status, errText);
      return NextResponse.json(
        { error: `Backend error: ${backendRes.status}` },
        { status: backendRes.status }
      );
    }

    const data = await backendRes.json();

    // Normalise backend ChatResponse → shape expected by /chat page UI
    const answer: string = data.answer ?? "";
    const runId: string = data.runId ?? data.run_id ?? "";
    const confidence: number = data.confidence ?? 0;
    const citations: Array<{ authority_id: string; cite: string; court: string; para_ids: number[] }> =
      data.citations ?? [];

    // Build structured citations for CitationsPanel
    const structuredCitations = citations.map((c) => ({
      type: "case",
      reference: c.cite || c.authority_id,
    }));

    // Compose DAO-style payload for the chat message UI
    const composedPayload = {
      run_id: runId,
      content: answer,
      final_verdict: "analysis_complete",
      final_confidence: confidence,
      explanation: {
        issue: query,
        rule: "Multi-agent legal analysis",
        application: answer,
        conclusion: answer,
      },
      next_steps: [],
      citations: structuredCitations,
      dao_details: null,
      verifier_status: confidence >= 0.7 ? "pass" : "review",
      verifier_notes: `Confidence: ${(confidence * 100).toFixed(1)}%`,
      audit: { run_id: runId },
      agent_outputs: [],
      agents: [
        "StatuteAgent",
        "PrecedentAgent",
        "LimitationAgent",
        "RiskAgent",
        "DevilAgent",
        "EthicsAgent",
        "DraftingAgent",
      ],
    };

    return NextResponse.json(composedPayload);
  } catch (error) {
    console.error("[chat/llm proxy] unexpected error:", error);
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 }
    );
  }
}
