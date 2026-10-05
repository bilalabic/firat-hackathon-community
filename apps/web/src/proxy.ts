import { NextResponse, type NextRequest } from "next/server";

import { isEventSlug } from "@/lib/routes";

// A malformed event slug ("BAD slug", too long, …) can never be published (the DB enforces the
// same pattern), so it gets a real 404 before any rendering or caching happens. Well-formed
// unknown slugs still reach the page, which answers them uncached (see [slug]/page.tsx).

// Not a route: rewriting to it renders app/not-found.tsx with HTTP 404.
const NOT_FOUND_PATH = "/_bulunamadi";

export function proxy(request: NextRequest) {
  const segment = request.nextUrl.pathname.split("/")[2] ?? "";
  let slug: string;
  try {
    slug = decodeURIComponent(segment);
  } catch {
    slug = "";
  }
  if (isEventSlug(slug)) return NextResponse.next();
  return NextResponse.rewrite(new URL(NOT_FOUND_PATH, request.url));
}

export const config = {
  matcher: "/hackathonlar/:path+",
};
