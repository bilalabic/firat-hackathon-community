import type { MetadataRoute } from "next";

import { getPublishedEvents } from "@/lib/events";
import { absoluteUrl, routes } from "@/lib/routes";

// Published events only (api.events_public), revalidated with the 'events' tag.
export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const events = await getPublishedEvents();
  const pages = [routes.home, routes.events, routes.community, routes.contribute, routes.about];
  return [
    ...pages.map((path) => ({ url: absoluteUrl(path) })),
    ...events.map((event) => ({
      url: absoluteUrl(routes.event(event.slug)),
      lastModified: new Date(event.updated_at),
    })),
  ];
}
