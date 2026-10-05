import type { Metadata } from "next";
import { Suspense } from "react";

import { Container, PageHeader } from "@/components/page-shell";
import { list } from "@/lib/copy";
import { getEventListing } from "@/lib/events";
import { routes } from "@/lib/routes";
import { cityOptions, defaultTab, parseListParams } from "@/lib/search";

import { EventExplorer } from "./event-explorer";

export const metadata: Metadata = {
  title: list.title,
  description: list.lead,
  alternates: { canonical: routes.events },
};

export default function EventsPage({ searchParams }: PageProps<"/hackathonlar">) {
  return (
    <Container>
      <PageHeader title={list.title} lead={list.lead} />
      {/* The events are cached; only reading the query string waits for the request. */}
      <Suspense fallback={<p className="py-10 text-muted-foreground">{list.loading}</p>}>
        <Explorer searchParams={searchParams} />
      </Suspense>
    </Container>
  );
}

async function Explorer({ searchParams }: Pick<PageProps<"/hackathonlar">, "searchParams">) {
  const [events, params] = await Promise.all([getEventListing(), searchParams]);
  return (
    <EventExplorer
      events={events}
      initialFilters={parseListParams(params, events)}
      defaultTab={defaultTab(events)}
      cities={cityOptions(events)}
    />
  );
}
