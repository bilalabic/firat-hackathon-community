import type { DetailedEvent } from "./event-types";
import { absoluteUrl, routes } from "./routes";

// The six characters backslash, "u003c": the JSON escape for "<".
const ESCAPED_LT = `${String.fromCharCode(92)}u003c`;

/**
 * JSON for a <script type="application/ld+json">. Escapes "<" so event content can never close
 * the script element or open an HTML comment. The element is not executed as JavaScript.
 */
export function serializeJsonLd(data: unknown): string {
  return JSON.stringify(data).replace(/</g, ESCAPED_LT);
}

const attendanceMode = {
  in_person: "https://schema.org/OfflineEventAttendanceMode",
  online: "https://schema.org/OnlineEventAttendanceMode",
  hybrid: "https://schema.org/MixedEventAttendanceMode",
} as const;

/** schema.org/Event for a published event (PUBLIC_WEB §4). */
export function eventJsonLd(event: DetailedEvent): Record<string, unknown> {
  const url = absoluteUrl(routes.event(event.slug));
  const physical =
    event.format !== "online" && (event.venue || event.city || event.country)
      ? {
          "@type": "Place",
          name: event.venue ?? event.city ?? event.country,
          address: {
            "@type": "PostalAddress",
            ...(event.city ? { addressLocality: event.city } : {}),
            ...(event.country ? { addressCountry: event.country } : {}),
          },
        }
      : null;
  const virtual =
    event.format === "online" || event.format === "hybrid"
      ? { "@type": "VirtualLocation", url: event.official_url }
      : null;
  const location = [physical, virtual].filter(Boolean);

  return {
    "@context": "https://schema.org",
    "@type": "Event",
    name: event.title,
    ...(event.summary ? { description: event.summary } : {}),
    ...(event.start_date ? { startDate: event.start_date } : {}),
    ...(event.end_date ?? event.start_date ? { endDate: event.end_date ?? event.start_date } : {}),
    eventStatus: "https://schema.org/EventScheduled",
    ...(event.format ? { eventAttendanceMode: attendanceMode[event.format] } : {}),
    ...(location.length === 1 ? { location: location[0] } : location.length > 1 ? { location } : {}),
    ...(event.organizer ? { organizer: { "@type": "Organization", name: event.organizer } } : {}),
    image: `${url}/opengraph-image`,
    url,
    sameAs: event.official_url,
  };
}
