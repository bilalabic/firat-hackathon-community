import { ApiErrorState } from "@/components/api-error-state"
import { EventsTable } from "@/components/events-table"
import { Pager } from "@/components/list-controls"
import { PageBody, Section } from "@/components/page-body"
import { SiteHeader } from "@/components/site-header"
import { api } from "@/lib/api/client"
import { toEventRow } from "@/lib/events"
import { PAGE_SIZE, pageOffset, parsePage } from "@/lib/paging"

/** Review queue: events in review. Each row opens the two-column review page. */
export default async function ReviewQueuePage({ searchParams }: PageProps<"/review">) {
  const page = parsePage(await searchParams)
  const result = await api.listEvents({
    status: ["in_review"],
    limit: PAGE_SIZE,
    offset: pageOffset(page),
  })

  return (
    <>
      <SiteHeader title="Review" />
      <PageBody>
        {result.ok ? (
          <>
            <EventsTable
              data={result.data.items.map((event) => toEventRow(event, "review"))}
              emptyText="Nothing is waiting for review."
              toolbar={
                <p className="text-sm text-muted-foreground">
                  Events in review. Open one to see its evidence and the review signals.
                </p>
              }
            />
            <Pager path="/review" params={{}} page={page} limit={PAGE_SIZE} total={result.data.total} />
          </>
        ) : (
          <Section>
            <ApiErrorState error={result.error} />
          </Section>
        )}
      </PageBody>
    </>
  )
}
