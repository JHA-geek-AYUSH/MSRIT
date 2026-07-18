import { NextRequest, NextResponse } from 'next/server';
import { auth } from '@clerk/nextjs/server';

// Shared global store — same reference as app/api/tasks/route.ts
const tasks: any[] = (global as any).__gemmaFin_tasks || [];
(global as any).__gemmaFin_tasks = tasks;

export async function GET(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { userId } = await auth();
  if (!userId) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });

  const { id } = await params;
  const task = tasks.find((t: any) => t.id === id && t.user_id === userId);
  if (!task) return NextResponse.json({ error: 'Task not found' }, { status: 404 });

  return NextResponse.json(task);
}
