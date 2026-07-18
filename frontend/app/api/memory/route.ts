import { NextRequest, NextResponse } from 'next/server';
import { auth } from '@clerk/nextjs/server';

// Shared global store so memory/search/route.ts can access the same data
const memories: any[] = (global as any).__gemmaFin_memories || [];
(global as any).__gemmaFin_memories = memories;

export async function GET(req: NextRequest) {
  const { userId } = await auth();
  if (!userId) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });

  const type = req.nextUrl.searchParams.get('type');
  const userMemories = memories.filter((m: any) => m.user_id === userId);
  const filtered = type ? userMemories.filter((m: any) => m.type === type) : userMemories;
  
  return NextResponse.json({
    memories: filtered.sort((a: any, b: any) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()),
  });
}

export async function POST(req: NextRequest) {
  const { userId } = await auth();
  if (!userId) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });

  const body = await req.json();
  const memory = {
    id: `mem_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
    user_id: userId,
    type: body.type || 'context',
    content: body.content,
    source: body.source || 'user_input',
    metadata: {},
    importance: body.importance || 5,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  };
  memories.push(memory);
  return NextResponse.json({ memory });
}

export async function DELETE(req: NextRequest) {
  const { userId } = await auth();
  if (!userId) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });

  const id = req.nextUrl.searchParams.get('id');
  const idx = memories.findIndex((m: any) => m.id === id && m.user_id === userId);
  if (idx === -1) return NextResponse.json({ error: 'Not found' }, { status: 404 });
  memories.splice(idx, 1);
  return NextResponse.json({ success: true });
}
