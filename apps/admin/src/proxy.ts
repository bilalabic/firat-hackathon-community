// Runs before every request (pages, Server Actions, route handlers, assets): rejects
// requests whose Host / X-Forwarded-Host / Origin is not an allowed admin host.
// This blocks DNS rebinding (SECURITY §4); the admin binds 127.0.0.1 only.

import { NextResponse, type NextRequest } from "next/server"

import { isAllowedRequest, parseAllowedHosts } from "@/lib/host-check"

export function proxy(request: NextRequest) {
  const allowedHosts = parseAllowedHosts(process.env.ADMIN_ALLOWED_HOSTS)
  const allowed = isAllowedRequest(
    {
      host: request.headers.get("host"),
      forwardedHost: request.headers.get("x-forwarded-host"),
      origin: request.headers.get("origin"),
    },
    allowedHosts
  )
  if (!allowed) {
    return new NextResponse("Bad request: host not allowed.\n", {
      status: 400,
      headers: { "content-type": "text/plain; charset=utf-8" },
    })
  }
  return NextResponse.next()
}
