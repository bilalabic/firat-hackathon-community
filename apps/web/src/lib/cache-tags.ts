import { z } from "zod";

// Cache tags of the event data (lib/events.ts) and the body of POST /api/revalidate:
// {"tags": ["events", "event:<slug>", …]}. Pure, unit-tested.

export const EVENTS_TAG = "events";
export const eventTag = (slug: string) => `event:${slug}`;

// Only the two tag shapes the data layer uses are accepted.
const tag = z.union([
  z.literal(EVENTS_TAG),
  z.string().max(86).regex(/^event:[a-z0-9]+(-[a-z0-9]+)*$/),
]);

export const revalidateBody = z.object({ tags: z.array(tag).min(1).max(50) }).strict();

/** The distinct tags to revalidate, or null if the body is invalid. */
export function parseRevalidateBody(json: unknown): string[] | null {
  const parsed = revalidateBody.safeParse(json);
  return parsed.success ? [...new Set(parsed.data.tags)] : null;
}
