"use server"

import { refresh } from "next/cache"
import { redirect } from "next/navigation"
import { z } from "zod"

import { api } from "@/lib/api/client"
import type { FormState } from "@/lib/form-state"
import { buildSourcePayload, readSourceForm, type SourceFormValues } from "@/lib/sources"

/** Form values as strings, for re-showing them after an error. */
function echo(values: SourceFormValues): Record<string, string> {
  return {
    ...values,
    enabled: values.enabled ? "on" : "",
    requires_js: values.requires_js ? "on" : "",
  }
}

export async function createSource(_prev: FormState, formData: FormData): Promise<FormState> {
  const values = readSourceForm(formData)
  const result = await api.createSource(buildSourcePayload(values))
  if (!result.ok) {
    return {
      status: "error",
      message: result.error.message,
      fieldErrors: result.error.fieldErrors,
      values: echo(values),
    }
  }
  redirect("/sources")
}

export async function updateSource(
  sourceId: string,
  _prev: FormState,
  formData: FormData
): Promise<FormState> {
  if (!z.uuid().safeParse(sourceId).success) return { status: "error", message: "Invalid source id." }
  const values = readSourceForm(formData)
  const result = await api.updateSource(sourceId, buildSourcePayload(values))
  if (!result.ok) {
    return {
      status: "error",
      message: result.error.message,
      fieldErrors: result.error.fieldErrors,
      values: echo(values),
    }
  }
  refresh()
  return { status: "success", message: "Saved." }
}
