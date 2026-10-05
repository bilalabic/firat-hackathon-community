import Link from "next/link"
import { PlusIcon } from "lucide-react"

import { ApiErrorState } from "@/components/api-error-state"
import { ExternalLink } from "@/components/external-link"
import { PageBody, Section } from "@/components/page-body"
import { SiteHeader } from "@/components/site-header"
import { Badge } from "@/components/ui/badge"
import { buttonVariants } from "@/components/ui/button"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { api } from "@/lib/api/client"
import { formatDateTime } from "@/lib/format"
import { humanize } from "@/lib/sources"

export default async function SourcesPage() {
  const result = await api.listSources()
  return (
    <>
      <SiteHeader title="Sources" />
      <PageBody>
        <Section className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-sm text-muted-foreground">
            Where events are found and confirmed. The tier sets how much a source counts as evidence.
          </p>
          <Link href="/sources/new" className={buttonVariants({ size: "sm" })}>
            <PlusIcon data-icon="inline-start" />
            New source
          </Link>
        </Section>
        <Section>
          {result.ok ? (
            <div className="overflow-hidden rounded-lg border">
              <Table>
                <TableHeader className="bg-muted">
                  <TableRow>
                    <TableHead>Name</TableHead>
                    <TableHead>Kind</TableHead>
                    <TableHead>Tier</TableHead>
                    <TableHead>Base URL</TableHead>
                    <TableHead>Retrieval</TableHead>
                    <TableHead>State</TableHead>
                    <TableHead>Updated</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {result.data.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={7} className="h-24 text-center text-muted-foreground">
                        No sources yet.
                      </TableCell>
                    </TableRow>
                  ) : (
                    result.data.map((source) => (
                      <TableRow key={source.id}>
                        <TableCell>
                          <Link href={`/sources/${source.id}`} className="font-medium underline-offset-4 hover:underline">
                            {source.name}
                          </Link>
                        </TableCell>
                        <TableCell>{humanize(source.kind)}</TableCell>
                        <TableCell className="tabular-nums">{source.tier}</TableCell>
                        <TableCell className="max-w-64">
                          <ExternalLink href={source.base_url} />
                        </TableCell>
                        <TableCell>
                          {humanize(source.retrieval_method)}
                          {source.requires_js ? " (JS)" : ""}
                        </TableCell>
                        <TableCell>
                          {source.enabled ? (
                            <Badge variant="outline">Enabled</Badge>
                          ) : (
                            <Badge variant="secondary">Disabled</Badge>
                          )}
                        </TableCell>
                        <TableCell className="whitespace-nowrap">{formatDateTime(source.updated_at)}</TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </div>
          ) : (
            <ApiErrorState error={result.error} />
          )}
        </Section>
      </PageBody>
    </>
  )
}
