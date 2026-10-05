import { safeHttpUrl } from "@/lib/urls"

/** Opens in a new tab without referrer; non-http(s) values are shown as text. */
export function ExternalLink({ href, children }: { href: string | null; children?: React.ReactNode }) {
  const safe = safeHttpUrl(href)
  if (!safe) return <>{href ?? "—"}</>
  return (
    <a href={safe} target="_blank" rel="noopener noreferrer" className="break-all underline-offset-4 hover:underline">
      {children ?? href}
    </a>
  )
}
