"use server"

import { refresh } from "next/cache"
import { redirect } from "next/navigation"

import { api } from "@/lib/api/client"
import type { ApiResult } from "@/lib/api/errors"
import type { FormState } from "@/lib/form-state"
import { isUuid } from "@/lib/params"
import { buildSourcePayload, readSourceForm, type SourceFormValues } from "@/lib/sources"

/** Form values as strings, for re-showing them after an error. */
function echo(values: SourceFormValues): Record<string, string> {
  return {
    ...values,
    enabled: values.enabled ? "on" : "",
    requires_js: values.requires_js ? "on" : "",
  }
}

/** Validates the form, sends it, and maps errors back to the form; null on success. */
async function submit(
  formData: FormData,
  send: (payload: ReturnType<typeof buildSourcePayload>["payload"]) => Promise<ApiResult<unknown>>
): Promise<FormState | null> {
  const values = readSourceForm(formData)
  const { payload, fieldErrors } = buildSourcePayload(values)
  if (Object.keys(fieldErrors).length > 0) {
    return { status: "error", message: "Some fields are invalid.", fieldErrors, values: echo(values) }
  }
  const result = await send(payload)
  if (result.ok) return null
  return {
    status: "error",
    message: result.error.message,
    fieldErrors: result.error.fieldErrors,
    values: echo(values),
  }
}

export async function createSource(_prev: FormState, formData: FormData): Promise<FormState> {
  const error = await submit(formData, (payload) => api.createSource(payload))
  if (error) return error
  redirect("/sources")
}

export async function updateSource(
  sourceId: string,
  _prev: FormState,
  formData: FormData
): Promise<FormState> {
  if (!isUuid(sourceId)) return { status: "error", message: "Invalid source id." }
  const error = await submit(formData, (payload) => api.updateSource(sourceId, payload))
  if (error) return error
  refresh()
  return { status: "success", message: "Saved." }
}
