import Link from "next/link"
import { ArrowRightIcon } from "lucide-react"

import { StatusDot } from "@/components/health-indicator"
import { Badge } from "@/components/ui/badge"
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import type { Heartbeat, Overview } from "@/lib/api/types"
import { formatAge, formatDateTime } from "@/lib/format"

type Counter = { label: string; value: number; href: string; hint: string; footer?: React.ReactNode }

function CounterCard({ label, value, href, hint, footer }: Counter) {
  return (
    <Card className="@container/card">
      <CardHeader>
        <CardDescription>{label}</CardDescription>
        <CardTitle className="text-2xl font-semibold tabular-nums @[250px]/card:text-3xl">
          {value}
        </CardTitle>
        <CardAction>
          <Link
            href={href}
            className="inline-flex items-center gap-1 rounded-sm text-sm text-muted-foreground underline-offset-4 outline-none hover:text-foreground hover:underline focus-visible:ring-3 focus-visible:ring-ring/50"
          >
            View
            <ArrowRightIcon className="size-3.5" aria-hidden />
            <span className="sr-only">{label}</span>
          </Link>
        </CardAction>
      </CardHeader>
      <CardFooter className="flex-col items-start gap-1.5 text-sm">
        <div className="text-muted-foreground">{hint}</div>
        {footer}
      </CardFooter>
    </Card>
  )
}

/** Overview counters (dashboard-01 SectionCards), each linking to its filtered list. */
export function SectionCards({ overview }: { overview: Overview }) {
  const counters: Counter[] = [
    {
      label: "In review",
      value: overview.in_review,
      href: "/events?status=in_review",
      hint: "Waiting for approve, reject or changes",
    },
    {
      label: "Published (upcoming)",
      value: overview.published_upcoming,
      href: "/events?view=upcoming",
      hint: "Published, last day today or later",
    },
    {
      label: "Closing in 7 days",
      value: overview.closing_within_7_days,
      href: "/events?view=closing",
      hint: "Published, deadline within 7 days",
    },
    {
      label: "New community applications",
      value: overview.new_community_applications,
      href: "/community-applications?status=new",
      hint: "Join Community form, status New",
      footer: (
        <Link
          href="/contributions?status=new"
          className="text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
        >
          {overview.new_team_applications} new team application
          {overview.new_team_applications === 1 ? "" : "s"}
        </Link>
      ),
    },
  ]
  return (
    <div className="grid grid-cols-1 gap-4 px-4 *:data-[slot=card]:shadow-xs lg:px-6 @xl/main:grid-cols-2 @5xl/main:grid-cols-4">
      {counters.map((counter) => (
        <CounterCard key={counter.label} {...counter} />
      ))}
    </div>
  )
}

const HEARTBEAT_LABELS: Record<Heartbeat["source"], string> = {
  vercel_cron: "Vercel Cron",
  github_actions: "GitHub Actions",
}

/** Supabase keep-alive heartbeats (D-19). The API marks a source stale after 48 h. */
export function HeartbeatsCard({ heartbeats }: { heartbeats: Heartbeat[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Keep-alive heartbeats</CardTitle>
        <CardDescription>Each scheduler must ping the database at least every 48 hours.</CardDescription>
      </CardHeader>
      <CardContent>
        <ul className="grid gap-3 @xl/main:grid-cols-2">
          {heartbeats.map((beat) => (
            <li key={beat.source} className="flex items-center justify-between gap-3 rounded-lg border p-3">
              <div className="flex min-w-0 items-center gap-2">
                <StatusDot level={beat.stale ? "error" : "ok"} />
                <div className="min-w-0">
                  <div className="font-medium">{HEARTBEAT_LABELS[beat.source]}</div>
                  <div className="truncate text-sm text-muted-foreground">
                    {beat.last_seen_at
                      ? `Last seen ${formatDateTime(beat.last_seen_at)} (${formatAge(beat.last_seen_at)})`
                      : "Never seen"}
                  </div>
                </div>
              </div>
              {beat.stale ? (
                <Badge variant="destructive">Stale</Badge>
              ) : (
                <Badge variant="outline">OK</Badge>
              )}
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  )
}
