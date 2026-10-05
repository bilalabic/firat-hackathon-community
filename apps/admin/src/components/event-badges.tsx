import { Badge } from "@/components/ui/badge"
import type { EventStatus, VerificationStatus } from "@/lib/api/types"
import { STATUS_LABELS, VERIFICATION_LABELS } from "@/lib/events"

const STATUS_VARIANT: Record<EventStatus, "default" | "secondary" | "outline" | "destructive"> = {
  draft: "outline",
  in_review: "secondary",
  approved: "secondary",
  published: "default",
  rejected: "destructive",
  archived: "outline",
}

export function EventStatusBadge({ status }: { status: EventStatus }) {
  return <Badge variant={STATUS_VARIANT[status]}>{STATUS_LABELS[status]}</Badge>
}

export function VerificationBadge({ status }: { status: VerificationStatus }) {
  return (
    <Badge variant="outline" className="text-muted-foreground">
      {VERIFICATION_LABELS[status]}
    </Badge>
  )
}
