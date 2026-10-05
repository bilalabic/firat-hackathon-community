import Link from "next/link"

import { EventStatusBadge, VerificationBadge } from "@/components/event-badges"
import { EventActionsBar } from "@/components/event-transitions"
import { buttonVariants } from "@/components/ui/button"
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import type { Event } from "@/lib/api/types"
import { formatDateTime } from "@/lib/format"

/** Status, timestamps and the allowed actions; shared by the edit and review pages. */
export function EventSummary({ event, link }: { event: Event; link: "edit" | "review" }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-2">
          <EventStatusBadge status={event.status} />
          <VerificationBadge status={event.verification_status} />
        </CardTitle>
        <CardDescription className="flex flex-wrap gap-x-4 gap-y-1">
          <span>Slug: {event.slug}</span>
          <span>Updated {formatDateTime(event.updated_at)}</span>
          {event.published_at && <span>Published {formatDateTime(event.published_at)}</span>}
          {event.archived_at && <span>Archived {formatDateTime(event.archived_at)}</span>}
        </CardDescription>
        <CardAction>
          {link === "review" ? (
            <Link href={`/events/${event.id}/review`} className={buttonVariants({ variant: "outline", size: "sm" })}>
              Open review
            </Link>
          ) : (
            <Link href={`/events/${event.id}`} className={buttonVariants({ variant: "outline", size: "sm" })}>
              Edit event
            </Link>
          )}
        </CardAction>
      </CardHeader>
      <CardContent>
        <EventActionsBar eventId={event.id} eventTitle={event.title} actions={event.allowed_actions} />
      </CardContent>
    </Card>
  )
}
