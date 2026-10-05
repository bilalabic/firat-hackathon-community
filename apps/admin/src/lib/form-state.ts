// State returned by form Server Actions (used with useActionState).

export type FormState = {
  status: "idle" | "error" | "success"
  message?: string
  fieldErrors?: Record<string, string>
  /** Submitted values, re-shown after an error (React resets the form after an action). */
  values?: Record<string, string>
}

export const IDLE: FormState = { status: "idle" }

/** Result of a Server Action called from an event handler (not a form). */
export type ActionResult = { ok: true; message: string } | { ok: false; message: string }
