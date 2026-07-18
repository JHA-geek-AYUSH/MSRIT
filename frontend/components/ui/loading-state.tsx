import { cn } from "@/lib/utils";

/** Themed skeleton loader (cream/brown palette) — replaces plain "Loading…" text
 * throughout the app for a richer perceived-performance UX. */
export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-lg bg-brown-500/10", className)} />;
}

export function CardSkeleton() {
  return (
    <div className="bg-stone-200/40 border border-brown-500/15 rounded-2xl p-6 space-y-3">
      <Skeleton className="h-4 w-1/3" />
      <Skeleton className="h-7 w-2/3" />
      <Skeleton className="h-3 w-full" />
      <Skeleton className="h-3 w-4/5" />
    </div>
  );
}

export function ListSkeleton({ rows = 4 }: { rows?: number }) {
  return (
    <div className="space-y-3">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="bg-stone-200/40 border border-brown-500/15 rounded-xl p-5 flex items-center justify-between">
          <div className="space-y-2 flex-1">
            <Skeleton className="h-4 w-1/2" />
            <Skeleton className="h-3 w-1/4" />
          </div>
          <Skeleton className="h-6 w-16 rounded-full" />
        </div>
      ))}
    </div>
  );
}

export function DashboardSkeleton() {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <CardSkeleton />
      <div className="lg:col-span-2">
        <ListSkeleton rows={3} />
      </div>
    </div>
  );
}
