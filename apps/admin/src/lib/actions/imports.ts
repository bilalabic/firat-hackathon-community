"use server"

// URL import (V1.2). Server Actions are reachable by direct POST, so the URL is checked
// here before it is sent to the API (which validates again).

import { refresh } from "next/cache"
import { redirect } from "next/navigation"

import { api } from "@/lib/api/client"
import type { FormState } from "@/lib/form-state"
import { parseImportUrl } from "@/lib/imports"

export type ImportFormState = FormState & {
  /** Set when an event with the same official URL already exists (nothing was created). */
  duplicateEventId?: string
}

export async function importFromUrl(_prev: ImportFormState, formData: FormData): Promise<ImportFormState> {
  const values = { url: String(formData.get("url") ?? "") }
  const parsed = parseImportUrl(values.url)
  if ("error" in parsed) {
    return { status: "error", message: parsed.error, fieldErrors: { url: parsed.error }, values }
  }

  const result = await api.importEventUrl({ url: parsed.url })
  // A run was (or may have been) recorded: re-render Recent imports.
  refresh()
  if (!result.ok) {
    const message =
      result.error.kind === "timeout"
        ? `${result.error.message} The import may still finish: check Recent imports below before trying again.`
        : result.error.message
    return { status: "error", message, fieldErrors: result.error.fieldErrors, values }
  }
  if (result.data.outcome === "duplicate") {
    return {
      status: "success",
      message: "An event with this official URL already exists. Nothing was imported.",
      duplicateEventId: result.data.event_id,
      values,
    }
  }
  redirect(`/events/${result.data.event_id}/review`)
}
