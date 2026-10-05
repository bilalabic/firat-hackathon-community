import type { ApplicationStatus } from "@/lib/api/types"

export const APPLICATION_STATUSES: readonly ApplicationStatus[] = [
  "new",
  "contacted",
  "accepted",
  "declined",
  "spam",
]

export const APPLICATION_STATUS_LABELS: Record<ApplicationStatus, string> = {
  new: "New",
  contacted: "Contacted",
  accepted: "Accepted",
  declined: "Declined",
  spam: "Spam",
}

export function isApplicationStatus(value: unknown): value is ApplicationStatus {
  return typeof value === "string" && (APPLICATION_STATUSES as readonly string[]).includes(value)
}
