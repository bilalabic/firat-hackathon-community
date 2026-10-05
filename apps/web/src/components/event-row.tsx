import { CalendarDays, MapPin } from "lucide-react";
import Link from "next/link";

import { common, eventRow } from "@/lib/copy";
import type { ListedEvent } from "@/lib/event-types";
import { dateParts, formatDate, formatDateRange, formatPlace } from "@/lib/format";
import { routes } from "@/lib/routes";
import { cn } from "@/lib/utils";

import { PhaseBadge } from "./phase-badge";

/** The date that matters most in the current phase: the deadline while open, else the event. */
function keyDate(event: ListedEvent): { label: string; date: string | null } {
  if (event.phase.phase === "open" && event.application_deadline) {
    return { label: eventRow.deadline, date: event.application_deadline };
  }
  return { label: eventRow.eventDate, date: event.start_date };
}

function DateBlock({ event }: { event: ListedEvent }) {
  const { label, date } = keyDate(event);
  const past = event.phase.phase === "past";
  const parts = date ? dateParts(date) : null;
  return (
    <div
      className={cn(
        "order-first flex w-16 shrink-0 flex-col items-center rounded-lg border py-2 text-center sm:w-20",
        past ? "text-muted-foreground" : "border-brand/25 bg-brand-soft text-brand",
      )}
    >
      <span aria-hidden="true" className="contents">
        <span className="text-[11px] leading-tight font-medium">{label}</span>
        {parts ? (
          <>
            <span className="text-2xl leading-none font-semibold tracking-tight tabular-nums sm:text-3xl">
              {parts.day}
            </span>
            <span className="text-xs leading-tight font-medium">{parts.month}</span>
          </>
        ) : (
          <span className="px-1 pt-1 text-[11px] leading-tight">{common.datesTba}</span>
        )}
      </span>
      <span className="sr-only">{`${label}: ${date ? formatDate(date) : common.datesTba}`}</span>
    </div>
  );
}

export function EventRow({ event, headingLevel = 3 }: { event: ListedEvent; headingLevel?: 2 | 3 }) {
  const Heading = headingLevel === 2 ? "h2" : "h3";
  return (
    <article className="group relative flex gap-4 py-5 sm:gap-6">
      <div className="min-w-0 flex-1 space-y-1.5">
        <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-1.5">
          <Heading className="text-base leading-snug font-semibold tracking-tight sm:text-lg">
            <Link
              href={routes.event(event.slug)}
              className="rounded-sm after:absolute after:inset-0 group-hover:underline group-hover:underline-offset-4"
            >
              {event.title}
            </Link>
          </Heading>
          <PhaseBadge phase={event.phase} />
        </div>
        {event.organizer ? <p className="text-sm text-muted-foreground">{event.organizer}</p> : null}
        <ul className="flex flex-wrap gap-x-4 gap-y-1 text-sm text-muted-foreground">
          <li className="flex items-center gap-1.5">
            <CalendarDays aria-hidden="true" className="size-4" />
            {formatDateRange(event.start_date, event.end_date)}
          </li>
          <li className="flex items-center gap-1.5">
            <MapPin aria-hidden="true" className="size-4" />
            {formatPlace(event)}
          </li>
        </ul>
      </div>
      {/* Visually first, but read after the title. */}
      <DateBlock event={event} />
    </article>
  );
}

export function EventList({ events, headingLevel }: { events: ListedEvent[]; headingLevel?: 2 | 3 }) {
  return (
    <ul className="divide-y border-y">
      {events.map((event) => (
        <li key={event.slug}>
          <EventRow event={event} headingLevel={headingLevel} />
        </li>
      ))}
    </ul>
  );
}
