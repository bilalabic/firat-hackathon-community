// Labels and UI metadata for events. Which actions are allowed always comes from the
// API (`allowed_actions`); this file only describes how each action is presented.

import type { Event, EventAction, EventStatus, VerificationStatus } from "@/lib/api/types"
import { formatDate, formatDateTime } from "@/lib/format"

export const EVENT_STATUSES: readonly EventStatus[] = [
  "draft",
  "in_review",
  "approved",
  "published",
  "rejected",
  "archived",
]

export const STATUS_LABELS: Record<EventStatus, string> = {
  draft: "Draft",
  in_review: "In review",
  approved: "Approved",
  published: "Published",
  rejected: "Rejected",
  archived: "Archived",
}

export const VERIFICATION_LABELS: Record<VerificationStatus, string> = {
  unverified: "Unverified",
  partially_verified: "Partially verified",
  verified: "Verified",
}

export function isEventStatus(value: unknown): value is EventStatus {
  return typeof value === "string" && (EVENT_STATUSES as readonly string[]).includes(value)
}

export type ActionMeta = {
  label: string
  /** Shown in a confirmation dialog before the action is sent. */
  confirm?: string
  /** Whether the dialog asks for a reason (stored in internal notes). */
  reason?: "required" | "optional"
  destructive?: boolean
}

export const ACTION_META: Record<EventAction, ActionMeta> = {
  submit: { label: "Submit for review" },
  approve: { label: "Approve" },
  reject: {
    label: "Reject",
    confirm: "The event moves to Rejected. The reason is appended to its internal notes.",
    reason: "required",
    destructive: true,
  },
  request_changes: {
    label: "Request changes",
    confirm: "The event goes back to Draft. An optional reason is appended to its internal notes.",
    reason: "optional",
  },
  publish: {
    label: "Publish",
    confirm: "The event appears on the public site, which is asked to revalidate.",
  },
  unpublish: {
    label: "Unpublish",
    confirm: "The event is removed from the public site and goes back to Approved.",
    destructive: true,
  },
  archive: {
    label: "Archive",
    confirm: "The event is archived. If it is published, it is removed from the public site.",
    destructive: true,
  },
  reopen: { label: "Reopen as draft" },
}

/** Actions that need a dialog (confirmation and/or reason) before they are sent. */
export function needsDialog(action: EventAction): boolean {
  const meta = ACTION_META[action]
  return Boolean(meta.confirm || meta.reason)
}

/** What the events table shows; dates are formatted on the server. */
export type EventRow = {
  id: string
  title: string
  slug: string
  status: EventStatus
  verification_status: VerificationStatus
  start: string
  deadline: string
  updated: string
  allowed_actions: EventAction[]
  /** Where the title links: the edit page, or the review page in the review queue. */
  href: string
}

export function toEventRow(event: Event, link: "edit" | "review" = "edit"): EventRow {
  return {
    id: event.id,
    href: link === "review" ? `/events/${event.id}/review` : `/events/${event.id}`,
    title: event.title,
    slug: event.slug,
    status: event.status,
    verification_status: event.verification_status,
    start: formatDate(event.start_date),
    deadline: formatDate(event.application_deadline),
    updated: formatDateTime(event.updated_at),
    allowed_actions: event.allowed_actions,
  }
}
