import { EventForm } from "@/components/event-form"
import { PageBody, Section } from "@/components/page-body"
import { SiteHeader } from "@/components/site-header"
import { createEvent } from "@/lib/actions/events"
import { EMPTY_EVENT_VALUES } from "@/lib/event-form"

export default function NewEventPage() {
  return (
    <>
      <SiteHeader title="New event" parents={[{ label: "Events", href: "/events" }]} />
      <PageBody>
        <Section>
          <p className="mb-4 text-sm text-muted-foreground">
            New events start as drafts. Title and official URL are required now; summary, start
            date and format are needed before the event can be submitted for review.
          </p>
          <EventForm action={createEvent} initialValues={EMPTY_EVENT_VALUES} submitLabel="Create draft" />
        </Section>
      </PageBody>
    </>
  )
}
