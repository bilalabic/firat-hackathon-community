import { cn } from "cn"

/** dashboard-01 content wrapper (container query + vertical rhythm). */
export function PageBody({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div className="flex flex-1 flex-col">
      <div className="@container/main flex flex-1 flex-col gap-2">
        <div className={cn("flex flex-col gap-4 py-4 md:gap-6 md:py-6", className)}>{children}</div>
      </div>
    </div>
  )
}

/** Horizontal padding used by every section inside PageBody. */
export function Section({ children, className }: { children: React.ReactNode; className?: string }) {
  return <section className={cn("px-4 lg:px-6", className)}>{children}</section>
}
