import { ArrowLeft, ExternalLink as ExternalIcon, Info } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { connection } from "next/server";
import { Suspense, type ReactNode } from "react";

import { ExternalLink } from "@/components/external-link";
import { Container } from "@/components/page-shell";
import { PhaseBadge } from "@/components/phase-badge";
import { buttonVariants } from "@/components/ui/button";
import { common, deadlineCountdown, detail, list, notFoundPage } from "@/lib/copy";
import type { DetailedEvent } from "@/lib/event-types";
import { getEvent, getPublishedEvents } from "@/lib/events";
import {
  formatDateRange,
  formatDateWithWeekday,
  formatLabel,
  formatLocation,
  formatMoney,
  formatUpdatedAt,
  safeExternalUrl,
} from "@/lib/format";
import { eventJsonLd, serializeJsonLd } from "@/lib/json-ld";
import { routes } from "@/lib/routes";
import { cn } from "@/lib/utils";

/**
 * The event, or the not-found page. For an unknown slug the not-found content is rendered at
 * request time (connection()), so a stale "not found" is never served after publishing. Next
 * still stores the route's generic shell for that URL; it is tagged 'events' + 'event:<slug>'
 * and expires with the 'events' cacheLife profile. Malformed slugs never get here (proxy.ts).
 */
async function getPublishedEventOr404(slug: string): Promise<DetailedEvent> {
  const event = await getEvent(slug);
  if (!event) {
    await connection();
    notFound();
  }
  return event;
}

export async function generateStaticParams() {
  const events = await getPublishedEvents();
  return events.map((event) => ({ slug: event.slug }));
}

export async function generateMetadata({ params }: PageProps<"/hackathonlar/[slug]">): Promise<Metadata> {
  const { slug } = await params;
  const event = await getEvent(slug);
  // The page itself calls notFound() (which adds the noindex tag once); here only a title.
  if (!event) return { title: notFoundPage.title };
  const description = event.summary ?? undefined;
  const path = routes.event(event.slug);
  return {
    title: event.title,
    description,
    alternates: { canonical: path },
    // The OpenGraph image comes from ./opengraph-image.tsx.
    openGraph: { type: "website", url: path, title: event.title, description },
    twitter: { card: "summary_large_image", title: event.title, description },
  };
}

export default function EventPage({ params }: PageProps<"/hackathonlar/[slug]">) {
  return (
    <Container className="max-w-4xl">
      <Suspense fallback={<p className="py-16 text-muted-foreground">{list.loading}</p>}>
        <EventDetail params={params} />
      </Suspense>
    </Container>
  );
}

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid gap-1 py-3 sm:grid-cols-[11rem_1fr] sm:gap-4">
      <dt className="text-sm text-muted-foreground">{label}</dt>
      <dd className="text-[15px]">{children}</dd>
    </div>
  );
}

function Deadline({ event }: { event: DetailedEvent }) {
  if (!event.application_deadline) return <>{common.notSpecified}</>;
  const { phase, daysLeft, closingSoon } = event.phase;
  return (
    <span className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
      <span>{formatDateWithWeekday(event.application_deadline)}</span>
      {phase === "open" && daysLeft !== null ? (
        <span className={cn("text-sm font-medium", closingSoon ? "text-soon" : "text-open")}>
          {deadlineCountdown(daysLeft)}
        </span>
      ) : (
        <span className="text-sm text-muted-foreground">{detail.deadlinePassed}</span>
      )}
    </span>
  );
}

function Chips({ items }: { items: string[] }) {
  return (
    <ul className="flex flex-wrap gap-1.5">
      {items.map((item) => (
        <li key={item} className="rounded-full border px-2.5 py-0.5 text-sm">
          {item}
        </li>
      ))}
    </ul>
  );
}

async function EventDetail({ params }: Pick<PageProps<"/hackathonlar/[slug]">, "params">) {
  const { slug } = await params;
  const event = await getPublishedEventOr404(slug);

  const officialUrl = safeExternalUrl(event.official_url);
  const applicationUrl = event.phase.phase === "open" ? safeExternalUrl(event.application_url) : null;
  const posterUrl = safeExternalUrl(event.poster_url);
  const prize =
    event.prize_pool !== null && event.currency ? formatMoney(event.prize_pool, event.currency) : null;

  return (
    <article className="pt-8 sm:pt-12">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: serializeJsonLd(eventJsonLd(event)) }}
      />
      <Link
        href={routes.events}
        className="inline-flex items-center gap-1.5 rounded-sm text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft aria-hidden="true" className="size-4" />
        {detail.back}
      </Link>

      <header className="space-y-4 pt-6 pb-8">
        <PhaseBadge phase={event.phase} />
        <h1 className="text-4xl leading-[1.05] font-semibold tracking-tight text-balance sm:text-5xl">
          {event.title}
        </h1>
        {event.organizer ? (
          <p className="text-lg text-muted-foreground">
            <span className="sr-only">{detail.organizer}: </span>
            {event.organizer}
          </p>
        ) : null}
        {event.summary ? <p className="max-w-[65ch] text-lg text-pretty">{event.summary}</p> : null}
        <div className="flex flex-wrap gap-3 pt-2">
          {applicationUrl ? (
            <ExternalLink href={applicationUrl} className={cn(buttonVariants(), "h-10 px-4")}>
              {detail.apply}
              <ExternalIcon aria-hidden="true" />
            </ExternalLink>
          ) : null}
          {officialUrl ? (
            <ExternalLink
              href={officialUrl}
              className={cn(buttonVariants({ variant: applicationUrl ? "outline" : "default" }), "h-10 px-4")}
            >
              {detail.officialPage}
              <ExternalIcon aria-hidden="true" />
            </ExternalLink>
          ) : null}
        </div>
      </header>

      {event.verification_status === "unverified" ? (
        <p className="mb-8 flex gap-2 rounded-lg border bg-muted px-4 py-3 text-sm">
          <Info aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
          {detail.unverified}
        </p>
      ) : null}

      <section aria-label={detail.factsLabel}>
        <dl className="divide-y border-y">
          <Fact label={detail.deadline}>
            <Deadline event={event} />
          </Fact>
          <Fact label={detail.dates}>{formatDateRange(event.start_date, event.end_date)}</Fact>
          <Fact label={detail.format}>{formatLabel(event.format)}</Fact>
          <Fact label={detail.location}>{formatLocation(event)}</Fact>
          <Fact label={detail.team}>{detail.teamSize(event.team_min, event.team_max)}</Fact>
          {event.eligibility ? <Fact label={detail.eligibility}>{event.eligibility}</Fact> : null}
          {prize ? <Fact label={detail.prize}>{prize}</Fact> : null}
          {event.is_free !== null ? (
            <Fact label={detail.fee}>{event.is_free ? detail.free : detail.paid}</Fact>
          ) : null}
        </dl>
      </section>

      {event.description ? (
        <section aria-labelledby="etkinlik-hakkinda" className="space-y-3 pt-10">
          <h2 id="etkinlik-hakkinda" className="text-xl font-semibold tracking-tight">
            {detail.about}
          </h2>
          <p className="max-w-[70ch] leading-relaxed whitespace-pre-line">{event.description}</p>
        </section>
      ) : null}

      {event.categories.length > 0 || event.technologies.length > 0 ? (
        <div className="grid gap-6 pt-10 sm:grid-cols-2">
          {event.categories.length > 0 ? (
            <section className="space-y-2" aria-label={detail.categories}>
              <h2 className="text-sm text-muted-foreground">{detail.categories}</h2>
              <Chips items={event.categories} />
            </section>
          ) : null}
          {event.technologies.length > 0 ? (
            <section className="space-y-2" aria-label={detail.technologies}>
              <h2 className="text-sm text-muted-foreground">{detail.technologies}</h2>
              <Chips items={event.technologies} />
            </section>
          ) : null}
        </div>
      ) : null}

      {posterUrl ? (
        // External poster as a plain <img> (PUBLIC_WEB §5: no remotePatterns configured yet).
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={posterUrl}
          alt={detail.posterAlt(event.title)}
          referrerPolicy="no-referrer"
          loading="lazy"
          className="mt-10 max-h-[32rem] w-auto rounded-lg border"
        />
      ) : null}

      <p className="pt-10 text-sm text-muted-foreground">
        {detail.lastUpdated}: <time dateTime={event.updated_at}>{formatUpdatedAt(event.updated_at)}</time>
      </p>
    </article>
  );
}
