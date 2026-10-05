import { Suspense } from "react"
import { notFound } from "next/navigation"

import { ApiErrorState } from "@/components/api-error-state"
import { AddEventSourceForm, RemoveEventSourceButton } from "@/components/event-source-controls"
import { EventSummary } from "@/components/event-summary"
import { PageBody, Section } from "@/components/page-body"
import { ReviewSignals, ReviewSignalsFallback } from "@/components/review-signals"
import { SiteHeader } from "@/components/site-header"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { api } from "@/lib/api/client"
import type { Event, EventSource, Source } from "@/lib/api/types"
import { ExternalLink } from "@/components/external-link"
import { STATUS_LABELS } from "@/lib/events"
import { formatDate, formatDateTime } from "@/lib/format"
import { isUuid } from "@/lib/params"
import { humanize } from "@/lib/sources"

function dash(value: React.ReactNode) {
  return value === null || value === undefined || value === "" ? "—" : value
}

function EventData({ event }: { event: Event }) {
  const place = [event.venue, event.city, event.country].filter(Boolean).join(", ")
  const team =
    event.team_min || event.team_max ? `${event.team_min ?? "?"}–${event.team_max ?? "?"}` : null
  const prize = event.prize_pool ? `${event.prize_pool} ${event.currency ?? ""}`.trim() : null
  const rows: [string, React.ReactNode][] = [
    ["Title", event.title],
    ["Status", STATUS_LABELS[event.status]],
    ["Organizer", dash(event.organizer)],
    ["Summary", dash(event.summary)],
    ["Format", event.format ? humanize(event.format) : "—"],
    ["Start", formatDate(event.start_date)],
    ["End", formatDate(event.end_date)],
    ["Application deadline", formatDate(event.application_deadline)],
    ["Timezone", event.timezone],
    ["Place", dash(place)],
    ["Official URL", <ExternalLink key="official" href={event.official_url} />],
    ["Application URL", <ExternalLink key="application" href={event.application_url} />],
    ["Team size", dash(team)],
    ["Prize pool", dash(prize)],
    ["Free", event.is_free === null ? "Unknown" : event.is_free ? "Yes" : "No"],
    ["Categories", dash(event.categories.join(", "))],
    ["Technologies", dash(event.technologies.join(", "))],
    ["Eligibility", dash(event.eligibility)],
    ["Description", dash(event.description)],
    ["Internal notes", dash(event.internal_notes)],
  ]
  return (
    <Card>
      <CardHeader>
        <CardTitle>Event data</CardTitle>
        <CardDescription>Created {formatDateTime(event.created_at)}</CardDescription>
      </CardHeader>
      <CardContent>
        <dl className="grid gap-x-4 gap-y-2 text-sm sm:grid-cols-[10rem_1fr]">
          {rows.map(([label, value]) => (
            <div key={label} className="contents">
              <dt className="text-muted-foreground">{label}</dt>
              <dd className="break-words whitespace-pre-line">{value}</dd>
            </div>
          ))}
        </dl>
      </CardContent>
    </Card>
  )
}

function EventSources({
  eventId,
  items,
  sources,
}: {
  eventId: string
  items: EventSource[]
  sources: Source[]
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Event sources</CardTitle>
        <CardDescription>Where this event is confirmed. Tiers come from the linked source.</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4">
        {items.length === 0 ? (
          <p className="text-sm text-muted-foreground">No sources yet.</p>
        ) : (
          <ul className="divide-y rounded-lg border">
            {items.map((item) => (
              <li key={item.id} className="flex items-start justify-between gap-3 p-3 text-sm">
                <div className="grid min-w-0 gap-1">
                  <ExternalLink href={item.url} />
                  <span className="text-muted-foreground">
                    {humanize(item.role)}
                    {item.source_name ? ` · ${item.source_name} (tier ${item.source_tier})` : " · no source"}
                    {item.last_http_status ? ` · last HTTP ${item.last_http_status}` : ""}
                  </span>
                </div>
                <RemoveEventSourceButton eventId={eventId} eventSourceId={item.id} url={item.url} />
              </li>
            ))}
          </ul>
        )}
        <AddEventSourceForm
          eventId={eventId}
          sources={sources.map((source) => ({ id: source.id, label: `${source.name} (tier ${source.tier})` }))}
        />
      </CardContent>
    </Card>
  )
}

export default async function EventReviewPage({ params }: PageProps<"/events/[id]/review">) {
  const { id } = await params
  if (!isUuid(id)) notFound()
  const [event, eventSources, sources] = await Promise.all([
    api.getEvent(id),
    api.listEventSources(id),
    api.listSources(),
  ])
  if (!event.ok && event.error.kind === "not_found") notFound()

  const parents = [{ label: "Review", href: "/review" }]
  if (!event.ok) {
    return (
      <>
        <SiteHeader title="Review" parents={parents} />
        <PageBody>
          <Section>
            <ApiErrorState error={event.error} />
          </Section>
        </PageBody>
      </>
    )
  }

  return (
    <>
      <SiteHeader title={event.data.title} parents={parents} />
      <PageBody>
        <Section>
          <EventSummary event={event.data} link="edit" />
        </Section>
        <Section className="grid items-start gap-4 @4xl/main:grid-cols-2">
          <EventData event={event.data} />
          <div className="grid gap-4">
            <h2 className="sr-only">Evidence</h2>
            <Suspense fallback={<ReviewSignalsFallback />}>
              <ReviewSignals eventId={id} />
            </Suspense>
            {eventSources.ok ? (
              <EventSources eventId={id} items={eventSources.data} sources={sources.ok ? sources.data : []} />
            ) : (
              <ApiErrorState error={eventSources.error} />
            )}
          </div>
        </Section>
      </PageBody>
    </>
  )
}
