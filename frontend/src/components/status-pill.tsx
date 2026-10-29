import { cn } from "../lib/utils.ts"

const dots: Record<string, string> = {
  success: "bg-chart-2",
  same: "bg-chart-2",
  failed: "bg-destructive",
  diverged: "bg-destructive",
  running: "bg-chart-4 motion-safe:animate-pulse",
  behind: "bg-chart-4",
  skipped: "bg-muted-foreground",
  never: "bg-muted-foreground",
  unknown: "bg-muted-foreground",
}

export function StatusPill({ status, labels }: { status: string; labels: Record<string, string> }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border bg-background/70 px-2.5 py-1 text-xs font-medium">
      <span className={cn("size-1.5 rounded-full", dots[status] ?? "bg-muted-foreground")} aria-hidden="true" />
      {labels[status] ?? status}
    </span>
  )
}
