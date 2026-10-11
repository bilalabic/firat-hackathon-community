import Link from "next/link"

import { ApiErrorState } from "@/components/api-error-state"
import { ExternalLink } from "@/components/external-link"
import { ImportUrlForm } from "@/components/import-url-form"
import { PageBody, Section } from "@/components/page-body"
import { SiteHeader } from "@/components/site-header"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { api } from "@/lib/api/client"
import type { ImportRun } from "@/lib/api/types"
import { formatDateTime } from "@/lib/format"
import { runState } from "@/lib/imports"

const RECENT_RUNS = 10

const STATE_BADGES = {
  running: { label: "Running", variant: "secondary" },
  interrupted: { label: "Interrupted", variant: "destructive" },
  succeeded: { label: "Created", variant: "default" },
  duplicate: { label: "Duplicate", variant: "outline" },
  failed: { label: "Failed", variant: "destructive" },
} as const

function RunItem({ run }: { run: ImportRun }) {
  const badge = STATE_BADGES[runState(run)]
  return (
    <li className="grid gap-1 p-3 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={badge.variant}>{badge.label}</Badge>
        <span className="text-muted-foreground">{formatDateTime(run.started_at)}</span>
        {run.event_id && (
          <Link href={`/events/${run.event_id}/review`} className="font-medium underline-offset-4 hover:underline">
            Open event
          </Link>
        )}
      </div>
      {run.url && <ExternalLink href={run.url} />}
      {run.error && <p className="break-words text-destructive">{run.error}</p>}
    </li>
  )
}

async function RecentImports() {
  const result = await api.listImportRuns({ limit: RECENT_RUNS })
  return (
    <Card className="max-w-3xl">
      <CardHeader>
        <CardTitle>Recent imports</CardTitle>
        <CardDescription>The last {RECENT_RUNS} URL imports, newest first.</CardDescription>
      </CardHeader>
      <CardContent>
        {!result.ok ? (
          <ApiErrorState error={result.error} />
        ) : result.data.items.length === 0 ? (
          <p className="text-sm text-muted-foreground">No imports yet.</p>
        ) : (
          <ul className="divide-y rounded-lg border">
            {result.data.items.map((run) => (
              <RunItem key={run.id} run={run} />
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}

export default function ImportEventPage() {
  return (
    <>
      <SiteHeader title="Import from URL" parents={[{ label: "Events", href: "/events" }]} />
      <PageBody>
        <Section>
          <p className="mb-4 max-w-3xl text-sm text-muted-foreground">
            The API fetches the page, reads its structured data (JSON-LD, meta tags) and asks the
            local LLM for the remaining fields. The result is a draft with the supporting snippet
            beside each field: check every value on the review page before submitting it. Pages
            that need JavaScript cannot be read yet; use{" "}
            <Link href="/events/new" className="underline underline-offset-4">
              New event
            </Link>{" "}
            for those.
          </p>
          <ImportUrlForm />
        </Section>
        <Section>
          <RecentImports />
        </Section>
      </PageBody>
    </>
  )
}
