import Link from "next/link"

import { ApiErrorState } from "@/components/api-error-state"
import { EventsTable } from "@/components/events-table"
import { PageBody, Section } from "@/components/page-body"
import { HeartbeatsCard, SectionCards } from "@/components/section-cards"
import { SiteHeader } from "@/components/site-header"
import { api } from "@/lib/api/client"
import { toEventRow } from "@/lib/events"

export default async function OverviewPage() {
  const [overview, events] = await Promise.all([api.overview(), api.listEvents({ limit: 10 })])

  return (
    <>
      <SiteHeader title="Overview" />
      <PageBody>
        {overview.ok ? (
          <>
            <SectionCards overview={overview.data} />
            <Section>
              <HeartbeatsCard heartbeats={overview.data.heartbeats} />
            </Section>
          </>
        ) : (
          <Section>
            <ApiErrorState error={overview.error} />
          </Section>
        )}
        {events.ok ? (
          <EventsTable
            data={events.data.items.map((event) => toEventRow(event))}
            toolbar={
              <>
                <h2 className="text-sm font-medium">Recently updated events</h2>
                <Link href="/events" className="text-sm text-muted-foreground underline-offset-4 hover:underline">
                  All events
                </Link>
              </>
            }
          />
        ) : (
          overview.ok && (
            <Section>
              <ApiErrorState error={events.error} />
            </Section>
          )
        )}
      </PageBody>
    </>
  )
}
