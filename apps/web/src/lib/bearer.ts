import "server-only";

import { createHash, timingSafeEqual } from "node:crypto";

/**
 * True if the request carries `Authorization: Bearer <secret>`. Constant-time: both sides are
 * hashed to equal-length digests before comparing. An unset or empty secret never matches.
 */
export function hasBearer(request: Request, secret: string | undefined): boolean {
  if (!secret) return false;
  const header = request.headers.get("authorization") ?? "";
  const match = /^Bearer (.+)$/.exec(header);
  if (!match) return false;
  const digest = (value: string) => createHash("sha256").update(value).digest();
  return timingSafeEqual(digest(match[1]), digest(secret));
}
