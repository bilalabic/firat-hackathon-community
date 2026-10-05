import { notFound } from "next/navigation"

import { ApiErrorState } from "@/components/api-error-state"
import { EventForm } from "@/components/event-form"
import { EventSummary } from "@/components/event-summary"
import { PageBody, Section } from "@/components/page-body"
import { SiteHeader } from "@/components/site-header"
import { updateEvent } from "@/lib/actions/events"
import { api } from "@/lib/api/client"
import { eventToFormValues } from "@/lib/event-form"
import { isUuid } from "@/lib/params"

export default async function EditEventPage({ params }: PageProps<"/events/[id]">) {
  const { id } = await params
  if (!isUuid(id)) notFound()
  const result = await api.getEvent(id)
  if (!result.ok && result.error.kind === "not_found") notFound()

  if (!result.ok) {
    return (
      <>
        <SiteHeader title="Event" parents={[{ label: "Events", href: "/events" }]} />
        <PageBody>
          <Section>
            <ApiErrorState error={result.error} />
          </Section>
        </PageBody>
      </>
    )
  }

  const event = result.data
  return (
    <>
      <SiteHeader title={event.title} parents={[{ label: "Events", href: "/events" }]} />
      <PageBody>
        <Section>
          <EventSummary event={event} link="review" />
        </Section>
        <Section>
          <EventForm
            action={updateEvent.bind(null, event.id)}
            initialValues={eventToFormValues(event)}
            submitLabel="Save changes"
          />
        </Section>
      </PageBody>
    </>
  )
}
