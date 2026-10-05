import { CircleAlertIcon, PlugZapIcon } from "lucide-react"

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import type { ApiError } from "@/lib/api/errors"

const TITLES: Partial<Record<ApiError["kind"], string>> = {
  unreachable: "API not reachable",
  timeout: "API timed out",
  config: "Admin is not configured",
  unauthorized: "API token rejected",
  unavailable: "Database unavailable",
  not_found: "Not found",
}

/** Full-width state for a page or section whose data could not be loaded. */
export function ApiErrorState({ error, className }: { error: ApiError; className?: string }) {
  const Icon = error.kind === "unreachable" || error.kind === "timeout" ? PlugZapIcon : CircleAlertIcon
  return (
    <Alert variant="destructive" className={className}>
      <Icon />
      <AlertTitle>{TITLES[error.kind] ?? "Request failed"}</AlertTitle>
      <AlertDescription>{error.message}</AlertDescription>
    </Alert>
  )
}

/** Inline message for a form or action result; announced to screen readers. */
export function FormMessage({
  status,
  message,
}: {
  status: "idle" | "error" | "success"
  message?: string
}) {
  if (!message || status === "idle") return null
  if (status === "error") {
    return (
      <Alert variant="destructive" tabIndex={-1} className="outline-none focus-visible:ring-3 focus-visible:ring-ring/50">
        <CircleAlertIcon />
        <AlertDescription>{message}</AlertDescription>
      </Alert>
    )
  }
  return (
    <p role="status" className="text-sm text-muted-foreground">
      {message}
    </p>
  )
}
