import { NextRequest, NextResponse } from 'next/server';
import { auth } from '@clerk/nextjs/server';

// Shared global store — same reference as app/api/memory/route.ts
const memories: any[] = (global as any).__gemmaFin_memories || [];
(global as any).__gemmaFin_memories = memories;

export async function GET(req: NextRequest) {
  const { userId } = await auth();
  if (!userId) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });

  const query = req.nextUrl.searchParams.get('q')?.toLowerCase() || '';
  const results = memories.filter((m: any) => 
    m.user_id === userId && m.content.toLowerCase().includes(query)
  );

  return NextResponse.json({ memories: results });
}
