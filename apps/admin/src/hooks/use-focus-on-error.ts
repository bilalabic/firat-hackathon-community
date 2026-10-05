"use client"

import { useEffect, useRef } from "react"

import type { FormState } from "@/lib/form-state"

/**
 * After a failed submit, moves focus to the first invalid field, or to the form's error
 * message when no field is marked. Runs after the fields were remounted with the
 * submitted values, so focus is not left on <body>.
 */
export function useFocusOnError(state: FormState) {
  const formRef = useRef<HTMLFormElement>(null)
  useEffect(() => {
    if (state.status !== "error") return
    const form = formRef.current
    const target =
      form?.querySelector<HTMLElement>('[aria-invalid="true"]') ??
      form?.querySelector<HTMLElement>('[data-slot="alert"]')
    target?.focus()
  }, [state])
  return formRef
}
