import { revalidateTag } from "next/cache";
import { z } from "zod";

import { hasBearer } from "@/lib/bearer";
import { EVENTS_TAG } from "@/lib/events";

// Called by FastAPI after publish, unpublish or edit (PUBLIC_WEB §2):
// POST, Authorization: Bearer <WEB_REVALIDATE_SECRET>, body {"tags": ["events", "event:<slug>"]}.

const tag = z.union([
  z.literal(EVENTS_TAG),
  z.string().max(86).regex(/^event:[a-z0-9]+(-[a-z0-9]+)*$/),
]);
const body = z.object({ tags: z.array(tag).min(1).max(50) }).strict();

export async function POST(request: Request) {
  if (!hasBearer(request, process.env.WEB_REVALIDATE_SECRET)) {
    return Response.json({ error: "unauthorized" }, { status: 401 });
  }

  let json: unknown;
  try {
    json = await request.json();
  } catch {
    return Response.json({ error: "invalid body" }, { status: 400 });
  }
  const parsed = body.safeParse(json);
  if (!parsed.success) {
    return Response.json({ error: "invalid tags" }, { status: 400 });
  }

  const tags = [...new Set(parsed.data.tags)];
  // {expire: 0}: the caller needs the old content gone immediately (D-07).
  for (const value of tags) revalidateTag(value, { expire: 0 });
  return Response.json({ revalidated: tags });
}
