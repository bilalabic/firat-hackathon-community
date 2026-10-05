"use client";

import { Search, X } from "lucide-react";
import { useEffect, useId, useMemo, useState, type MouseEvent } from "react";

import { EventList } from "@/components/event-row";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { formatLabels, list, tabLabels } from "@/lib/copy";
import type { ListedEvent } from "@/lib/event-types";
import {
  formatFromSlug,
  formatSlugs,
  listParams,
  routes,
  tabSlugs,
  type EventFormat,
  type TabSlug,
} from "@/lib/routes";
import { countByTab, filterEvents, toQueryString, type ListFilters } from "@/lib/search";
import { cn } from "@/lib/utils";

type Props = {
  events: ListedEvent[];
  initialFilters: ListFilters;
  defaultTab: TabSlug;
  cities: string[];
};

// Filtering runs in the browser over the already-sent events (PUBLIC_WEB §2). The server
// renders the same result from the query string, so the page works without JavaScript too
// (the filter form is a plain GET form).
export function EventExplorer({ events, initialFilters, defaultTab, cities }: Props) {
  const [filters, setFilters] = useState(initialFilters);
  const ids = { query: useId(), format: useId(), city: useId() };

  const results = useMemo(() => filterEvents(events, filters), [events, filters]);
  const counts = useMemo(() => countByTab(events, filters), [events, filters]);
  const filtered = filters.query.trim() !== "" || filters.format !== null || filters.city !== null;

  // Keep the URL shareable. Next.js syncs native history updates with its router.
  useEffect(() => {
    const query = toQueryString(filters, defaultTab);
    if (query !== window.location.search) {
      window.history.replaceState(null, "", `${routes.events}${query}`);
    }
  }, [filters, defaultTab]);

  const update = (patch: Partial<ListFilters>) => setFilters((current) => ({ ...current, ...patch }));

  const selectTab = (tab: TabSlug) => (event: MouseEvent<HTMLAnchorElement>) => {
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
    event.preventDefault();
    update({ tab });
  };

  const clear = () => update({ query: "", format: null, city: null });

  return (
    <div className="space-y-6">
      <form
        role="search"
        aria-label={list.filtersLabel}
        method="get"
        action={routes.events}
        onSubmit={(event) => event.preventDefault()}
        className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto_auto] sm:items-end"
      >
        {filters.tab !== defaultTab ? <input type="hidden" name={listParams.tab} value={filters.tab} /> : null}
        <div className="space-y-1.5">
          <Label htmlFor={ids.query}>{list.searchLabel}</Label>
          <div className="relative">
            <Search
              aria-hidden="true"
              className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"
            />
            <Input
              id={ids.query}
              type="search"
              name={listParams.query}
              value={filters.query}
              onChange={(event) => update({ query: event.target.value })}
              placeholder={list.searchPlaceholder}
              autoComplete="off"
              maxLength={100}
              className="h-10 pl-9"
            />
          </div>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor={ids.format}>{list.formatLabel}</Label>
          <NativeSelect
            id={ids.format}
            name={listParams.format}
            value={filters.format ? formatSlugs[filters.format] : ""}
            onChange={(event) => update({ format: formatFromSlug(event.target.value) ?? null })}
            className="w-full sm:w-44 [&_select]:h-10"
          >
            <NativeSelectOption value="">{list.formatAll}</NativeSelectOption>
            {(Object.keys(formatSlugs) as EventFormat[]).map((format) => (
              <NativeSelectOption key={format} value={formatSlugs[format]}>
                {formatLabels[format]}
              </NativeSelectOption>
            ))}
          </NativeSelect>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor={ids.city}>{list.cityLabel}</Label>
          <NativeSelect
            id={ids.city}
            name={listParams.city}
            value={filters.city ?? ""}
            onChange={(event) => update({ city: event.target.value || null })}
            className="w-full sm:w-44 [&_select]:h-10"
          >
            <NativeSelectOption value="">{list.cityAll}</NativeSelectOption>
            {cities.map((city) => (
              <NativeSelectOption key={city} value={city}>
                {city}
              </NativeSelectOption>
            ))}
          </NativeSelect>
        </div>
        <noscript>
          <Button type="submit" className="h-10 px-4">
            {list.submit}
          </Button>
        </noscript>
      </form>

      <nav aria-label={list.tabsLabel} className="-mx-4 overflow-x-auto px-4 sm:mx-0 sm:px-0">
        <ul className="flex min-w-max gap-1 border-b">
          {tabSlugs.map((tab) => {
            const current = filters.tab === tab;
            return (
              <li key={tab}>
                <a
                  href={`${routes.events}${toQueryString({ ...filters, tab }, defaultTab)}`}
                  onClick={selectTab(tab)}
                  aria-current={current ? "page" : undefined}
                  className={cn(
                    "-mb-px inline-flex min-h-11 items-center gap-2 border-b-2 px-3 text-sm transition-colors",
                    current
                      ? "border-foreground font-medium text-foreground"
                      : "border-transparent text-muted-foreground hover:text-foreground",
                  )}
                >
                  {tabLabels[tab]}
                  <span
                    className={cn(
                      "rounded-full px-1.5 text-xs tabular-nums",
                      current ? "bg-foreground text-background" : "bg-muted text-muted-foreground",
                    )}
                  >
                    {counts[tab]}
                  </span>
                </a>
              </li>
            );
          })}
        </ul>
      </nav>

      <div className="flex flex-wrap items-center justify-between gap-2">
        <p aria-live="polite" className="text-sm text-muted-foreground">
          {list.resultCount(results.length)}
        </p>
        {filtered ? (
          <Button type="button" variant="ghost" size="sm" onClick={clear}>
            <X aria-hidden="true" />
            {list.clear}
          </Button>
        ) : null}
      </div>

      {results.length > 0 ? (
        <EventList events={results} headingLevel={2} />
      ) : (
        <p className="border-y py-10 text-muted-foreground">
          {filtered ? list.emptyFiltered : list.emptyTab[filters.tab]}
        </p>
      )}
    </div>
  );
}
