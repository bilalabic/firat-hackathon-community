"use server"

// Status changes for community and team applications. These rows are personal data:
// nothing here logs them, and only the status is returned to the browser.

import { refresh } from "next/cache"
import { z } from "zod"

import { api } from "@/lib/api/client"
import { APPLICATION_STATUSES } from "@/lib/applications"
import type { ApplicationStatus } from "@/lib/api/types"
import type { ActionResult } from "@/lib/form-state"

const input = z.object({
  kind: z.enum(["community", "team"]),
  id: z.uuid(),
  status: z.enum(APPLICATION_STATUSES as [ApplicationStatus, ...ApplicationStatus[]]),
})

export async function updateApplicationStatus(value: {
  kind: "community" | "team"
  id: string
  status: ApplicationStatus
}): Promise<ActionResult> {
  const parsed = input.safeParse(value)
  if (!parsed.success) return { ok: false, message: "Invalid status change." }
  const { kind, id, status } = parsed.data
  const result =
    kind === "community"
      ? await api.updateCommunityApplication(id, { status })
      : await api.updateTeamApplication(id, { status })
  if (!result.ok) return { ok: false, message: result.error.message }
  refresh()
  return { ok: true, message: "Status updated." }
}
