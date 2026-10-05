import { ArrowRight } from "lucide-react";
import Link from "next/link";

import { EventList } from "@/components/event-row";
import { Container, Section } from "@/components/page-shell";
import { buttonVariants } from "@/components/ui/button";
import { common, home } from "@/lib/copy";
import { getEventListing } from "@/lib/events";
import { routes } from "@/lib/routes";
import { filterEvents } from "@/lib/search";
import { cn } from "@/lib/utils";

const noFilters = { query: "", format: null, city: null } as const;
const UPCOMING_PREVIEW = 3;

function SeeAll({ href }: { href: string }) {
  return (
    <Link href={href} className="inline-flex items-center gap-1 text-sm font-medium text-brand hover:underline">
      {common.seeAll}
      <ArrowRight aria-hidden="true" className="size-4" />
    </Link>
  );
}

export default async function HomePage() {
  const events = await getEventListing();
  const closingSoon = filterEvents(events, { ...noFilters, tab: "son-gunler" });
  const open = filterEvents(events, { ...noFilters, tab: "acik" });
  const openLater = open.filter((event) => !event.phase.closingSoon);
  const upcoming = filterEvents(events, { ...noFilters, tab: "yaklasan" });

  return (
    <Container>
      <section className="max-w-3xl space-y-5 pt-14 pb-10 sm:pt-20 sm:pb-14">
        <h1 className="text-5xl leading-[1.02] font-semibold tracking-tighter text-balance sm:text-7xl">
          {home.title}
        </h1>
        <p className="max-w-[60ch] text-lg text-pretty text-muted-foreground">{home.lead}</p>
        <p className="text-lg font-medium text-pretty">
          {home.summary(open.length, closingSoon.length, upcoming.length)}
        </p>
        <div className="flex flex-wrap gap-3 pt-2">
          <Link href={routes.events} className={cn(buttonVariants(), "h-10 px-4")}>
            {common.allEvents}
          </Link>
          <Link href={routes.community} className={cn(buttonVariants({ variant: "outline" }), "h-10 px-4")}>
            {home.communityCta}
          </Link>
        </div>
      </section>

      {closingSoon.length > 0 ? (
        <Section
          id="son-gunler"
          title={home.closingSoonTitle}
          lead={home.closingSoonLead}
          action={<SeeAll href={routes.eventsTab("son-gunler")} />}
        >
          <EventList events={closingSoon} />
        </Section>
      ) : null}

      {openLater.length > 0 ? (
        <Section
          id="basvurular-acik"
          title={home.openTitle}
          lead={home.openLead}
          action={<SeeAll href={routes.eventsTab("acik")} />}
        >
          <EventList events={openLater} />
        </Section>
      ) : null}

      {open.length === 0 && upcoming.length > 0 ? (
        <Section
          id="yaklasan"
          title={home.upcomingTitle}
          lead={home.upcomingLead}
          action={<SeeAll href={routes.eventsTab("yaklasan")} />}
        >
          <EventList events={upcoming.slice(0, UPCOMING_PREVIEW)} />
        </Section>
      ) : null}

      <section className="mt-10 grid gap-8 border-t pt-10 sm:grid-cols-2">
        <div className="space-y-3">
          <h2 className="text-xl font-semibold tracking-tight">{home.communityTitle}</h2>
          <p className="text-muted-foreground">{home.communityLead}</p>
          <Link href={routes.community} className="inline-flex items-center gap-1 font-medium text-brand hover:underline">
            {home.communityCta}
            <ArrowRight aria-hidden="true" className="size-4" />
          </Link>
        </div>
        <div className="space-y-3">
          <h2 className="text-xl font-semibold tracking-tight">{home.suggestTitle}</h2>
          <p className="text-muted-foreground">{home.suggestLead}</p>
          <Link href={routes.community} className="inline-flex items-center gap-1 font-medium text-brand hover:underline">
            {home.suggestCta}
            <ArrowRight aria-hidden="true" className="size-4" />
          </Link>
        </div>
      </section>
    </Container>
  );
}
