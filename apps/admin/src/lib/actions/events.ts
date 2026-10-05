"use server"

// Event mutations. Server Actions are reachable by direct POST, so every input is
// validated here before it is sent to the API (which validates again).

import { refresh } from "next/cache"
import { redirect } from "next/navigation"
import { z } from "zod"

import { api } from "@/lib/api/client"
import type { EventAction, EventSourceRole } from "@/lib/api/types"
import {
  buildEventPayload,
  changedFields,
  readEventForm,
} from "@/lib/event-form"
import { ACTION_META, STATUS_LABELS } from "@/lib/events"
import type { ActionResult, FormState } from "@/lib/form-state"
import { EVENT_SOURCE_ROLES } from "@/lib/sources"

const LOCAL_INVALID = "Some fields are invalid. Fix the marked fields and try again."
const uuid = z.uuid()

const ACTIONS = Object.keys(ACTION_META) as [EventAction, ...EventAction[]]

export async function createEvent(_prev: FormState, formData: FormData): Promise<FormState> {
  const values = readEventForm(formData)
  const { payload, fieldErrors } = buildEventPayload(values)
  if (Object.keys(fieldErrors).length > 0) {
    return { status: "error", message: LOCAL_INVALID, fieldErrors, values }
  }
  const result = await api.createEvent(payload)
  if (!result.ok) {
    return {
      status: "error",
      message: result.error.message,
      fieldErrors: result.error.fieldErrors,
      values,
    }
  }
  redirect(`/events/${result.data.id}`)
}

export async function updateEvent(
  eventId: string,
  _prev: FormState,
  formData: FormData
): Promise<FormState> {
  if (!uuid.safeParse(eventId).success) return { status: "error", message: "Invalid event id." }
  const values = readEventForm(formData)
  const { payload, fieldErrors } = buildEventPayload(values)
  if (Object.keys(fieldErrors).length > 0) {
    return { status: "error", message: LOCAL_INVALID, fieldErrors, values }
  }

  // PATCH only what changed: an unchanged save must not bump updated_at or
  // revalidate the public site.
  const current = await api.getEvent(eventId)
  if (!current.ok) return { status: "error", message: current.error.message, values }
  const changes = changedFields(payload, current.data)
  if (Object.keys(changes).length === 0) {
    return { status: "success", message: "No changes to save." }
  }

  const result = await api.updateEvent(eventId, changes)
  if (!result.ok) {
    return {
      status: "error",
      message: result.error.message,
      fieldErrors: result.error.fieldErrors,
      values,
    }
  }
  refresh()
  const published = result.data.status === "published"
  return {
    status: "success",
    message: published
      ? "Saved. The public site is asked to revalidate this event."
      : "Saved.",
  }
}

const transitionInput = z.object({
  eventId: uuid,
  action: z.enum(ACTIONS),
  reason: z.string().trim().max(1000).optional(),
})

export async function transitionEvent(input: {
  eventId: string
  action: EventAction
  reason?: string
}): Promise<ActionResult> {
  const parsed = transitionInput.safeParse(input)
  if (!parsed.success) return { ok: false, message: "Invalid transition request." }
  const { eventId, action, reason } = parsed.data

  const result = await api.transitionEvent(eventId, { action, reason: reason || null })
  if (!result.ok) {
    // 409 usually means the page was stale: re-render it so the actions offered
    // match the current status. The message stays visible.
    if (result.error.kind === "conflict") refresh()
    return { ok: false, message: result.error.message }
  }
  refresh()
  return {
    ok: true,
    message: `${ACTION_META[action].label}: done. Status is now ${STATUS_LABELS[result.data.status]}.`,
  }
}

const sourceInput = z.object({
  url: z.string(),
  role: z.enum(EVENT_SOURCE_ROLES as [EventSourceRole, ...EventSourceRole[]]),
  source_id: z.union([z.literal(""), uuid]),
})

export async function addEventSource(
  eventId: string,
  _prev: FormState,
  formData: FormData
): Promise<FormState> {
  const values = {
    url: String(formData.get("url") ?? ""),
    role: String(formData.get("role") ?? ""),
    source_id: String(formData.get("source_id") ?? ""),
  }
  const parsed = sourceInput.safeParse(values)
  if (!uuid.safeParse(eventId).success || !parsed.success) {
    return { status: "error", message: "Invalid event source.", values }
  }
  const result = await api.addEventSource(eventId, {
    url: parsed.data.url,
    role: parsed.data.role,
    source_id: parsed.data.source_id || null,
  })
  if (!result.ok) {
    return {
      status: "error",
      message: result.error.message,
      fieldErrors: result.error.fieldErrors,
      values,
    }
  }
  refresh()
  return { status: "success", message: "Source added." }
}

export async function removeEventSource(input: {
  eventId: string
  eventSourceId: string
}): Promise<ActionResult> {
  if (!uuid.safeParse(input.eventId).success || !uuid.safeParse(input.eventSourceId).success) {
    return { ok: false, message: "Invalid event source id." }
  }
  const result = await api.removeEventSource(input.eventId, input.eventSourceId)
  if (!result.ok) return { ok: false, message: result.error.message }
  refresh()
  return { ok: true, message: "Source removed." }
}
