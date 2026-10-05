"use client"

import * as React from "react"
import Link from "next/link"
import {
  CalendarDaysIcon,
  ClipboardCheckIcon,
  DatabaseIcon,
  HandHeartIcon,
  LayoutDashboardIcon,
  Settings2Icon,
  UsersIcon,
} from "lucide-react"

import { NavMain, type NavItem } from "@/components/nav-main"
import { NavSecondary } from "@/components/nav-secondary"
import {
  Sidebar,
  SidebarContent,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar"

// V1 navigation (docs/architecture/LOCAL_ADMIN.md "Navigation"). Discovery, Runs and
// Publishing are hidden until their versions; Telegram is checked under Settings.
const navMain: NavItem[] = [
  { title: "Overview", url: "/", icon: <LayoutDashboardIcon /> },
  { title: "Events", url: "/events", icon: <CalendarDaysIcon /> },
  { title: "Review", url: "/review", icon: <ClipboardCheckIcon /> },
  { title: "Community Applications", url: "/community-applications", icon: <UsersIcon /> },
  { title: "Contributions", url: "/contributions", icon: <HandHeartIcon /> },
  { title: "Sources", url: "/sources", icon: <DatabaseIcon /> },
]

const navSecondary: NavItem[] = [{ title: "Settings", url: "/settings", icon: <Settings2Icon /> }]

export function AppSidebar({ ...props }: React.ComponentProps<typeof Sidebar>) {
  return (
    <Sidebar collapsible="offcanvas" {...props}>
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton
              className="data-[slot=sidebar-menu-button]:p-1.5!"
              render={<Link href="/" />}
            >
              <span className="text-base font-semibold">FHC Admin</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>
      <SidebarContent>
        <NavMain items={navMain} />
        <NavSecondary items={navSecondary} className="mt-auto" />
      </SidebarContent>
    </Sidebar>
  )
}
