// Server-rendered filter links and pager for list pages (state lives in the URL).

import Link from "next/link"
import { ChevronLeftIcon, ChevronRightIcon } from "lucide-react"
import { cn } from "cn"

import { buttonVariants } from "@/components/ui/button"
import { hrefWith } from "@/lib/paging"

export type FilterOption = { label: string; href: string; active: boolean }

export function FilterLinks({ label, options }: { label: string; options: FilterOption[] }) {
  return (
    <nav aria-label={label} className="flex flex-wrap items-center gap-1">
      {options.map((option) => (
        <Link
          key={option.href}
          href={option.href}
          aria-current={option.active ? "page" : undefined}
          className={cn(buttonVariants({ variant: option.active ? "secondary" : "ghost", size: "sm" }))}
        >
          {option.label}
        </Link>
      ))}
    </nav>
  )
}

export function Pager({
  path,
  params,
  page,
  limit,
  total,
}: {
  path: string
  /** Current filters, kept on every page link. */
  params: Record<string, string | undefined>
  page: number
  limit: number
  total: number
}) {
  const pages = Math.max(1, Math.ceil(total / limit))
  const from = total === 0 ? 0 : (page - 1) * limit + 1
  const to = Math.min(total, page * limit)
  const link = (target: number) => hrefWith(path, { ...params, page: target > 1 ? target : undefined })
  const button = cn(buttonVariants({ variant: "outline", size: "sm" }))
  const disabled = cn(button, "pointer-events-none opacity-50")

  return (
    <nav aria-label="Pagination" className="flex items-center justify-between gap-4 px-4 text-sm lg:px-6">
      <p className="text-muted-foreground">
        {total === 0 ? "No results" : `${from}–${to} of ${total}`}
      </p>
      <div className="flex items-center gap-2">
        <span className="hidden font-medium sm:inline">
          Page {Math.min(page, pages)} of {pages}
        </span>
        {page > 1 ? (
          <Link href={link(page - 1)} className={button}>
            <ChevronLeftIcon aria-hidden />
            Previous
          </Link>
        ) : (
          <span aria-disabled className={disabled}>
            <ChevronLeftIcon aria-hidden />
            Previous
          </span>
        )}
        {page < pages ? (
          <Link href={link(page + 1)} className={button}>
            Next
            <ChevronRightIcon aria-hidden />
          </Link>
        ) : (
          <span aria-disabled className={disabled}>
            Next
            <ChevronRightIcon aria-hidden />
          </span>
        )}
      </div>
    </nav>
  )
}
