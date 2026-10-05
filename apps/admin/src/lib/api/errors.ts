// Turns failed API calls into one error shape with an English, operator-facing message.
// Pure (no server-only import) so it can be unit tested.

export type ApiErrorKind =
  | "config"
  | "unreachable"
  | "timeout"
  | "bad_request"
  | "unauthorized"
  | "not_found"
  | "conflict"
  | "validation"
  | "unavailable"
  | "server"

export type ApiError = {
  kind: ApiErrorKind
  /** HTTP status, or null when no response was received. */
  status: number | null
  message: string
  /** 422 field errors keyed by request-body field name. */
  fieldErrors: Record<string, string>
}

export type ApiResult<T> = { ok: true; data: T } | { ok: false; error: ApiError }

export const API_START_HINT =
  "Start it with `pnpm --filter api dev` (or `uv run uvicorn fhc_api.main:create_app_from_env --factory` in services/api)."

export function configError(message: string): ApiError {
  return { kind: "config", status: null, message, fieldErrors: {} }
}

export function unreachableError(baseUrl: string): ApiError {
  return {
    kind: "unreachable",
    status: null,
    message: `API not reachable at ${baseUrl}. ${API_START_HINT}`,
    fieldErrors: {},
  }
}

export function timeoutError(seconds: number): ApiError {
  return {
    kind: "timeout",
    status: null,
    message: `The API did not answer within ${seconds} s.`,
    fieldErrors: {},
  }
}

type FastApiFieldError = { loc?: unknown; msg?: unknown }

function cleanMessage(msg: string): string {
  // Pydantic prefixes custom validator messages with "Value error, ".
  return msg.replace(/^Value error, /, "")
}

/** FastAPI request-validation errors: `[{loc: ["body", field, ...], msg}]`. */
function splitValidationErrors(detail: FastApiFieldError[]): {
  fieldErrors: Record<string, string>
  general: string[]
} {
  const fieldErrors: Record<string, string> = {}
  const general: string[] = []
  for (const item of detail) {
    const loc = Array.isArray(item.loc) ? item.loc : []
    const msg = cleanMessage(typeof item.msg === "string" ? item.msg : "is invalid")
    if (loc[0] === "body" && typeof loc[1] === "string") {
      const field = loc[1]
      fieldErrors[field] = fieldErrors[field] ? `${fieldErrors[field]}; ${msg}` : msg
    } else {
      const where = loc.filter((part) => part !== "body").join(".")
      general.push(where ? `${where}: ${msg}` : msg)
    }
  }
  return { fieldErrors, general }
}

function detailText(body: unknown): string | null {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail
    if (typeof detail === "string" && detail.trim()) return detail
  }
  return null
}

export function parseErrorResponse(status: number, body: unknown): ApiError {
  const detail = detailText(body)
  const base = { status, fieldErrors: {} }

  switch (status) {
    case 400:
      return { ...base, kind: "bad_request", message: sentence(`The API rejected the request: ${detail ?? "bad request"}`) }
    case 401:
      return {
        ...base,
        kind: "unauthorized",
        message:
          "The API rejected the admin token (401). ADMIN_API_TOKEN in apps/admin/.env.local must match services/api/.env.",
      }
    case 404:
      return { ...base, kind: "not_found", message: sentence(detail ?? "not found") }
    case 409:
      return { ...base, kind: "conflict", message: sentence(detail ?? "conflict") }
    case 422: {
      const raw = body && typeof body === "object" ? (body as { detail?: unknown }).detail : null
      if (Array.isArray(raw)) {
        const { fieldErrors, general } = splitValidationErrors(raw as FastApiFieldError[])
        const message = general.length
          ? sentence(general.join("; "))
          : "Some fields are invalid. Fix the marked fields and try again."
        return { status, kind: "validation", message, fieldErrors }
      }
      return { ...base, kind: "validation", message: sentence(detail ?? "invalid input") }
    }
    case 503:
      return {
        ...base,
        kind: "unavailable",
        message: `The API cannot reach the database (${detail ?? "service unavailable"}).`,
      }
    default:
      return {
        ...base,
        kind: "server",
        message: `The API failed with HTTP ${status}${detail ? `: ${detail}` : ""}.`,
      }
  }
}

/** Capitalized, ending with a period (API details are lower-case fragments). */
function sentence(text: string): string {
  const trimmed = text.trim()
  const capitalized = trimmed.charAt(0).toUpperCase() + trimmed.slice(1)
  return /[.!?]$/.test(capitalized) ? capitalized : `${capitalized}.`
}
