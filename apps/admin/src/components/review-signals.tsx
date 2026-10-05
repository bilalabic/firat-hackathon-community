// Deterministic review signals from GET /events/{id}/review. Rules only, no scores.

import Link from "next/link"
import { CircleCheckIcon, CircleXIcon, InfoIcon, TriangleAlertIcon } from "lucide-react"
import { cn } from "cn"

import { ApiErrorState } from "@/components/api-error-state"
import { EventStatusBadge } from "@/components/event-badges"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { api } from "@/lib/api/client"
import type { Review, Signal } from "@/lib/api/types"

const SIGNAL_LABELS: Record<Signal["key"], string> = {
  official_url_reachable: "Official URL reachable",
  registration_url_present: "Registration URL present",
  dates_coherent: "Dates coherent",
  deadline_missing: "Deadline missing",
  deadline_passed: "Deadline passed",
  possible_duplicate: "Possible duplicate",
  supporting_sources: "Supporting sources",
}

const STATUS_ICON = {
  pass: { Icon: CircleCheckIcon, className: "text-emerald-600 dark:text-emerald-400", label: "Pass" },
  warn: { Icon: TriangleAlertIcon, className: "text-amber-600 dark:text-amber-400", label: "Warning" },
  fail: { Icon: CircleXIcon, className: "text-destructive", label: "Fail" },
  info: { Icon: InfoIcon, className: "text-muted-foreground", label: "Info" },
} as const

const MATCH_LABELS = { official_url: "same official URL", title_and_start_date: "same title and start date" }

function SignalItem({ signal }: { signal: Signal }) {
  const { Icon, className, label } = STATUS_ICON[signal.status]
  return (
    <li className="flex gap-3 py-2">
      <Icon className={cn("mt-0.5 size-4 shrink-0", className)} aria-hidden />
      <div className="grid min-w-0 gap-0.5">
        <div className="flex flex-wrap items-center gap-2 font-medium">
          <span>{SIGNAL_LABELS[signal.key]}</span>
          <span className="sr-only">: {label}.</span>
          {signal.blocks_approval && <Badge variant="destructive">Blocks approval</Badge>}
        </div>
        <p className="text-sm break-words text-muted-foreground">{signal.detail}</p>
      </div>
    </li>
  )
}

function ReviewDetails({ review }: { review: Review }) {
  return (
    <>
      <ul className="divide-y">
        {review.signals.map((signal) => (
          <SignalItem key={signal.key} signal={signal} />
        ))}
      </ul>
      {review.duplicates.length > 0 && (
        <div className="mt-4 grid gap-2">
          <h3 className="text-sm font-medium">Possible duplicates</h3>
          <ul className="grid gap-2">
            {review.duplicates.map((duplicate) => (
              <li key={duplicate.id} className="flex flex-wrap items-center gap-2 text-sm">
                <Link href={`/events/${duplicate.id}/review`} className="font-medium underline-offset-4 hover:underline">
                  {duplicate.title}
                </Link>
                <EventStatusBadge status={duplicate.status} />
                <span className="text-muted-foreground">
                  ({duplicate.matches.map((match) => MATCH_LABELS[match]).join(", ")})
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
      <p className="mt-4 text-sm text-muted-foreground">
        Sources by tier:{" "}
        {review.sources_by_tier.length === 0
          ? "none"
          : review.sources_by_tier
              .map((tier) => `${tier.tier === null ? "no source" : `tier ${tier.tier}`}: ${tier.count}`)
              .join(", ")}
      </p>
    </>
  )
}

function SignalsCard({ children }: { children: React.ReactNode }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Review signals</CardTitle>
        <CardDescription>Deterministic checks. Failing checks marked “Blocks approval” make approve and publish fail.</CardDescription>
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  )
}

export async function ReviewSignals({ eventId }: { eventId: string }) {
  const result = await api.getReview(eventId)
  return (
    <SignalsCard>
      {result.ok ? <ReviewDetails review={result.data} /> : <ApiErrorState error={result.error} />}
    </SignalsCard>
  )
}

export function ReviewSignalsFallback() {
  return (
    <SignalsCard>
      <p className="mb-3 text-sm text-muted-foreground" role="status">
        Checking the official URL and computing signals…
      </p>
      <div className="grid gap-3">
        {Array.from({ length: 5 }, (_, index) => (
          <Skeleton key={index} className="h-8 w-full" />
        ))}
      </div>
    </SignalsCard>
  )
}
