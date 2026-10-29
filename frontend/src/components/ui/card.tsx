import type { HTMLAttributes } from "react"
import { cn } from "../../lib/utils.ts"

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("rounded-xl border bg-card text-card-foreground shadow-sm", className)} {...props} />
}

export function Badge({ className, ...props }: HTMLAttributes<HTMLSpanElement>) {
  return <span className={cn("inline-flex items-center rounded-full border bg-secondary px-2.5 py-0.5 text-xs font-medium text-secondary-foreground", className)} {...props} />
}
