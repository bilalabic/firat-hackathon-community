// Shared frame for the two application lists: status filter, table, pager.
// Personal data is rendered here on the server and never logged.

import { ApiErrorState } from "@/components/api-error-state"
import { FilterLinks, Pager } from "@/components/list-controls"
import { PageBody, Section } from "@/components/page-body"
import { SiteHeader } from "@/components/site-header"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import type { ApiResult } from "@/lib/api/errors"
import type { ApplicationStatus } from "@/lib/api/types"
import { APPLICATION_STATUSES, APPLICATION_STATUS_LABELS, isApplicationStatus } from "@/lib/applications"
import { PAGE_SIZE, firstParam, hrefWith, pageOffset, parsePage, type SearchParams } from "@/lib/paging"

export type Column<T> = { header: string; cell: (row: T) => React.ReactNode; className?: string }

export function parseApplicationParams(params: SearchParams) {
  const statusParam = firstParam(params, "status")
  const status = isApplicationStatus(statusParam) ? statusParam : undefined
  const page = parsePage(params)
  return {
    status,
    page,
    query: {
      ...(status ? { status: [status] } : {}),
      limit: PAGE_SIZE,
      offset: pageOffset(page),
    },
  }
}

export function ApplicationsList<T extends { id: string }>({
  title,
  path,
  description,
  status,
  page,
  result,
  columns,
}: {
  title: string
  path: string
  description: string
  status: ApplicationStatus | undefined
  page: number
  result: ApiResult<{ items: T[]; total: number }>
  columns: Column<T>[]
}) {
  const filters = [
    { label: "All", href: path, active: !status },
    ...APPLICATION_STATUSES.map((value) => ({
      label: APPLICATION_STATUS_LABELS[value],
      href: hrefWith(path, { status: value }),
      active: status === value,
    })),
  ]

  return (
    <>
      <SiteHeader title={title} />
      <PageBody>
        <Section className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-sm text-muted-foreground">{description}</p>
          <FilterLinks label={`Filter ${title.toLowerCase()}`} options={filters} />
        </Section>
        {result.ok ? (
          <>
            <Section>
              <div className="overflow-hidden rounded-lg border">
                <Table>
                  <TableHeader className="bg-muted">
                    <TableRow>
                      {columns.map((column) => (
                        <TableHead key={column.header}>{column.header}</TableHead>
                      ))}
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {result.data.items.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={columns.length} className="h-24 text-center text-muted-foreground">
                          No applications{status ? ` with status ${APPLICATION_STATUS_LABELS[status]}` : ""}.
                        </TableCell>
                      </TableRow>
                    ) : (
                      result.data.items.map((row) => (
                        <TableRow key={row.id}>
                          {columns.map((column) => (
                            <TableCell key={column.header} className={column.className ?? "align-top"}>
                              {column.cell(row)}
                            </TableCell>
                          ))}
                        </TableRow>
                      ))
                    )}
                  </TableBody>
                </Table>
              </div>
            </Section>
            <Pager path={path} params={{ status }} page={page} limit={PAGE_SIZE} total={result.data.total} />
          </>
        ) : (
          <Section>
            <ApiErrorState error={result.error} />
          </Section>
        )}
      </PageBody>
    </>
  )
}

/** Long free text in a table cell: wraps, keeps line breaks, capped width. */
export function LongText({ value }: { value: string | null }) {
  if (!value) return <span className="text-muted-foreground">—</span>
  return <p className="max-w-xs text-sm break-words whitespace-pre-line">{value}</p>
}
