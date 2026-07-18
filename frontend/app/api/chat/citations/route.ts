import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/**
 * POST /api/chat/citations
 *
 * Fetches real Indian legal citations from the backend, which queries the
 * Indian Kanoon API for authoritative Indian case law and statute references.
 *
 * Previously returned hardcoded US-law mock citations — now production-ready.
 */
export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { query, caseType, jurisdiction, limit = 10 } = body;

    if (!query?.trim()) {
      return NextResponse.json(
        { error: "Query is required", citations: [] },
        { status: 400 }
      );
    }

    // Build search params for the backend /v1/search endpoint
    const params = new URLSearchParams();
    params.set("q", query);
    params.set("limit", String(Math.min(limit, 50)));
    params.set("ik_source", "true");

    if (caseType) params.set("type", caseType);

    const res = await fetch(`${BACKEND_URL}/v1/search?${params.toString()}`, {
      method: "GET",
      headers: { "Content-Type": "application/json" },
      signal: AbortSignal.timeout(15_000),
    });

    if (!res.ok) {
      const errText = await res.text().catch(() => "Unknown error");
      console.error("[citations] backend error:", res.status, errText);
      return NextResponse.json(
        { error: `Backend error: ${res.status}`, citations: [] },
        { status: res.status }
      );
    }

    const data = await res.json();

    // Transform search results into citation cards
    const citations = (data.results ?? []).map((r: any, idx: number) => ({
      id: r.id ?? String(idx + 1),
      title: r.title ?? "Unknown",
      source: r.source ?? r.type ?? "Indian Kanoon",
      excerpt: r.excerpt ?? r.description ?? "",
      relevanceScore: r.relevance_score ?? 0.5,
      url: r.url ?? `https://indiankanoon.org/doc/${r.docid ?? r.id}/`,
    }));

    return NextResponse.json({
      citations,
      total: data.total ?? citations.length,
      query,
      caseType,
      jurisdiction,
      took: data.took ?? 0,
    });
  } catch (error) {
    console.error("Error in citations API:", error);
    return NextResponse.json(
      {
        error: "Failed to fetch citations. Please try again.",
        citations: [],
      },
      { status: 500 }
    );
  }
}
