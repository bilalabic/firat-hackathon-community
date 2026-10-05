import { revalidateTag } from "next/cache";

import { hasBearer } from "@/lib/bearer";
import { parseRevalidateBody } from "@/lib/cache-tags";

// Called by FastAPI after publish, unpublish or edit (PUBLIC_WEB §2):
// POST, Authorization: Bearer <WEB_REVALIDATE_SECRET>, body {"tags": ["events", "event:<slug>"]}.

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
  const tags = parseRevalidateBody(json);
  if (!tags) {
    return Response.json({ error: "invalid tags" }, { status: 400 });
  }

  // {expire: 0}: the caller needs the old content gone immediately (D-07).
  for (const value of tags) revalidateTag(value, { expire: 0 });
  return Response.json({ revalidated: tags });
}
