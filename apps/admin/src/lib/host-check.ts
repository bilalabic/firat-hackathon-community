// Host allow-list for the admin (SECURITY §4: DNS rebinding). Pure; used by src/proxy.ts.
//
// A rebinding page is served from the attacker's host name, so its requests carry that
// name in Host (and in Origin). Requests are accepted only when Host, and X-Forwarded-Host
// and Origin when present, name an allowed host. Next.js compares Origin with
// X-Forwarded-Host / Host for Server Actions, so all three must be checked.

/** Default: loopback names only. An entry without a port allows any port. */
export const DEFAULT_ALLOWED_HOSTS = ["127.0.0.1", "localhost"]

/** `ADMIN_ALLOWED_HOSTS="127.0.0.1,localhost:3001"`; empty or unset → the default. */
export function parseAllowedHosts(value: string | undefined): string[] {
  const entries = (value ?? "")
    .split(",")
    .map((entry) => entry.trim().toLowerCase())
    .filter(Boolean)
  return entries.length > 0 ? entries : DEFAULT_ALLOWED_HOSTS
}

/** Splits "name:port" (also "[::1]:port"); null when the value is not a plain host. */
function splitHost(value: string): { name: string; port: string | null } | null {
  const match = /^(\[[0-9a-f:.]+\]|[a-z0-9.-]+)(?::(\d{1,5}))?$/.exec(value.trim().toLowerCase())
  return match ? { name: match[1], port: match[2] ?? null } : null
}

export function isAllowedHost(host: string | null | undefined, allowed: string[]): boolean {
  if (!host) return false
  const parsed = splitHost(host)
  if (!parsed) return false
  return allowed.some((entry) => {
    const rule = splitHost(entry)
    if (!rule || rule.name !== parsed.name) return false
    return rule.port === null || rule.port === parsed.port
  })
}

function originHost(origin: string): string | null {
  try {
    const url = new URL(origin)
    return url.protocol === "http:" || url.protocol === "https:" ? url.host : null
  } catch {
    return null // includes the opaque origin "null"
  }
}

export function isAllowedRequest(
  headers: { host: string | null; forwardedHost: string | null; origin: string | null },
  allowed: string[]
): boolean {
  if (!isAllowedHost(headers.host, allowed)) return false
  if (headers.forwardedHost !== null && !isAllowedHost(headers.forwardedHost, allowed)) return false
  if (headers.origin !== null && !isAllowedHost(originHost(headers.origin), allowed)) return false
  return true
}
