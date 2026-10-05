import Link from "next/link"
import { PlusIcon } from "lucide-react"

import { ApiErrorState } from "@/components/api-error-state"
import { EventsTable } from "@/components/events-table"
import { FilterLinks, Pager, type FilterOption } from "@/components/list-controls"
import { PageBody, Section } from "@/components/page-body"
import { SiteHeader } from "@/components/site-header"
import { buttonVariants } from "@/components/ui/button"
import { api } from "@/lib/api/client"
import { EVENT_STATUSES, STATUS_LABELS, isEventStatus, toEventRow } from "@/lib/events"
import { PAGE_SIZE, firstParam, hrefWith, pageOffset, parsePage } from "@/lib/paging"

const VIEWS = {
  upcoming: { label: "Upcoming (published)", query: { upcoming: true } },
  closing: { label: "Closing in 7 days", query: { closing_within_days: 7 } },
} as const

type View = keyof typeof VIEWS
const isView = (value: unknown): value is View => typeof value === "string" && value in VIEWS

export default async function EventsPage({ searchParams }: PageProps<"/events">) {
  const params = await searchParams
  const statusParam = firstParam(params, "status")
  const viewParam = firstParam(params, "view")
  const status = isEventStatus(statusParam) ? statusParam : undefined
  const view = !status && isView(viewParam) ? viewParam : undefined
  const page = parsePage(params)

  const result = await api.listEvents({
    ...(status ? { status: [status] } : {}),
    ...(view ? VIEWS[view].query : {}),
    limit: PAGE_SIZE,
    offset: pageOffset(page),
  })

  const filters: FilterOption[] = [
    { label: "All", href: "/events", active: !status && !view },
    ...EVENT_STATUSES.map((value) => ({
      label: STATUS_LABELS[value],
      href: hrefWith("/events", { status: value }),
      active: status === value,
    })),
    ...(Object.keys(VIEWS) as View[]).map((value) => ({
      label: VIEWS[value].label,
      href: hrefWith("/events", { view: value }),
      active: view === value,
    })),
  ]

  return (
    <>
      <SiteHeader title="Events" />
      <PageBody>
        {result.ok ? (
          <>
            <EventsTable
              data={result.data.items.map((event) => toEventRow(event))}
              emptyText="No events match this filter."
              toolbar={
                <>
                  <Link href="/events/new" className={buttonVariants({ size: "sm" })}>
                    <PlusIcon data-icon="inline-start" />
                    New event
                  </Link>
                  <FilterLinks label="Filter events" options={filters} />
                </>
              }
            />
            <Pager
              path="/events"
              params={{ status, view }}
              page={page}
              limit={PAGE_SIZE}
              total={result.data.total}
            />
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
