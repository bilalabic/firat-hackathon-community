"use client"

// dashboard-01 DataTable adapted to events: no drag handle, no row selection,
// server-side paging (see Pagination), column visibility kept.

import * as React from "react"
import Link from "next/link"
import {
  columnVisibilityFeature,
  createColumnHelper,
  FlexRender,
  tableFeatures,
  useTable,
  type ColumnVisibilityState,
} from "@tanstack/react-table"
import { ChevronDownIcon, Columns3Icon } from "lucide-react"

import { EventRowActions } from "@/components/event-transitions"
import { EventStatusBadge, VerificationBadge } from "@/components/event-badges"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import type { EventRow } from "@/lib/events"

const features = tableFeatures({ columnVisibilityFeature })
const columnHelper = createColumnHelper<typeof features, EventRow>()

const columns = columnHelper.columns([
  columnHelper.accessor("title", {
    header: "Title",
    cell: ({ row }) => (
      <div className="flex max-w-md flex-col">
        <Link
          href={row.original.href}
          className="truncate font-medium underline-offset-4 hover:underline"
        >
          {row.original.title}
        </Link>
        <span className="truncate text-xs text-muted-foreground">{row.original.slug}</span>
      </div>
    ),
    enableHiding: false,
  }),
  columnHelper.accessor("status", {
    header: "Status",
    cell: ({ row }) => <EventStatusBadge status={row.original.status} />,
  }),
  columnHelper.accessor("verification_status", {
    id: "verification",
    header: "Verification",
    cell: ({ row }) => <VerificationBadge status={row.original.verification_status} />,
  }),
  columnHelper.accessor("start", { header: "Start", cell: ({ getValue }) => <span className="tabular-nums">{getValue()}</span> }),
  columnHelper.accessor("deadline", { header: "Deadline", cell: ({ getValue }) => <span className="tabular-nums">{getValue()}</span> }),
  columnHelper.accessor("updated", { header: "Updated", cell: ({ getValue }) => <span className="whitespace-nowrap">{getValue()}</span> }),
  columnHelper.display({
    id: "actions",
    header: () => <span className="sr-only">Actions</span>,
    cell: ({ row }) => (
      <EventRowActions
        eventId={row.original.id}
        eventTitle={row.original.title}
        actions={row.original.allowed_actions}
      />
    ),
  }),
])

export function EventsTable({
  data,
  toolbar,
  emptyText = "No events.",
}: {
  data: EventRow[]
  toolbar?: React.ReactNode
  emptyText?: string
}) {
  const [columnVisibility, setColumnVisibility] = React.useState<ColumnVisibilityState>({})
  const table = useTable({
    features,
    data,
    columns,
    state: { columnVisibility },
    getRowId: (row) => row.id,
    onColumnVisibilityChange: setColumnVisibility,
  })

  return (
    <div className="flex w-full flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2 px-4 lg:px-6">
        <div className="flex flex-wrap items-center gap-2">{toolbar}</div>
        <DropdownMenu>
          <DropdownMenuTrigger render={<Button variant="outline" size="sm" />}>
            <Columns3Icon data-icon="inline-start" />
            Columns
            <ChevronDownIcon data-icon="inline-end" />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-40">
            {table
              .getAllColumns()
              .filter((column) => typeof column.accessorFn !== "undefined" && column.getCanHide())
              .map((column) => (
                <DropdownMenuCheckboxItem
                  key={column.id}
                  className="capitalize"
                  checked={column.getIsVisible()}
                  onCheckedChange={(value) => column.toggleVisibility(!!value)}
                >
                  {column.id}
                </DropdownMenuCheckboxItem>
              ))}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
      <div className="px-4 lg:px-6">
        <div className="overflow-hidden rounded-lg border">
          <Table>
            <TableHeader className="sticky top-0 z-10 bg-muted">
              {table.getHeaderGroups().map((headerGroup) => (
                <TableRow key={headerGroup.id}>
                  {headerGroup.headers.map((header) => (
                    <TableHead key={header.id} colSpan={header.colSpan}>
                      {header.isPlaceholder ? null : <FlexRender header={header} />}
                    </TableHead>
                  ))}
                </TableRow>
              ))}
            </TableHeader>
            <TableBody>
              {table.getRowModel().rows.length ? (
                table.getRowModel().rows.map((row) => (
                  <TableRow key={row.id}>
                    {row.getVisibleCells().map((cell) => (
                      <TableCell key={cell.id}>
                        <FlexRender cell={cell} />
                      </TableCell>
                    ))}
                  </TableRow>
                ))
              ) : (
                <TableRow>
                  <TableCell colSpan={columns.length} className="h-24 text-center text-muted-foreground">
                    {emptyText}
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
      </div>
    </div>
  )
}
