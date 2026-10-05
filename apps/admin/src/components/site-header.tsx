import { Fragment, Suspense } from "react"
import Link from "next/link"

import { HealthIndicator, HealthIndicatorFallback } from "@/components/health-indicator"
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb"
import { Separator } from "@/components/ui/separator"
import { SidebarTrigger } from "@/components/ui/sidebar"

export type Crumb = { label: string; href: string }

/** Page title with optional parent breadcrumbs, and the health indicator. */
export function SiteHeader({ title, parents = [] }: { title: string; parents?: Crumb[] }) {
  return (
    <header className="flex h-(--header-height) shrink-0 items-center gap-2 border-b transition-[width,height] ease-linear group-has-data-[collapsible=icon]/sidebar-wrapper:h-(--header-height)">
      <div className="flex w-full min-w-0 items-center gap-1 px-4 lg:gap-2 lg:px-6">
        <SidebarTrigger className="-ml-1" />
        <Separator orientation="vertical" className="mx-2 h-4 data-vertical:self-auto" />
        {parents.length > 0 && (
          <Breadcrumb className="hidden md:block">
            <BreadcrumbList className="flex-nowrap">
              {parents.map((crumb) => (
                <Fragment key={crumb.href}>
                  <BreadcrumbItem>
                    <BreadcrumbLink render={<Link href={crumb.href} />}>{crumb.label}</BreadcrumbLink>
                  </BreadcrumbItem>
                  <BreadcrumbSeparator />
                </Fragment>
              ))}
            </BreadcrumbList>
          </Breadcrumb>
        )}
        <h1 className="min-w-0 truncate text-base font-medium">{title}</h1>
        <div className="ml-auto shrink-0">
          <Suspense fallback={<HealthIndicatorFallback />}>
            <HealthIndicator />
          </Suspense>
        </div>
      </div>
    </header>
  )
}
