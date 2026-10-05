// Source and event-source vocabularies (mirroring the API's Literal types) and the
// source form conversion. Pure.

import type { EventSourceRole, RetrievalMethod, Source, SourceCreate, SourceKind } from "@/lib/api/types"

export const SOURCE_KINDS: readonly SourceKind[] = [
  "organizer_site",
  "event_platform",
  "social",
  "aggregator",
  "university",
  "community",
  "manual",
]

export const RETRIEVAL_METHODS: readonly RetrievalMethod[] = [
  "manual",
  "api",
  "json_endpoint",
  "rss",
  "html",
  "browser",
]

export const EVENT_SOURCE_ROLES: readonly EventSourceRole[] = [
  "official",
  "registration",
  "discovery",
  "announcement",
]

export const TIERS = [1, 2, 3, 4] as const

/** "event_platform" -> "Event platform" */
export function humanize(value: string): string {
  const text = value.replace(/_/g, " ")
  return text.charAt(0).toUpperCase() + text.slice(1)
}

export type SourceFormValues = Record<
  "name" | "kind" | "tier" | "base_url" | "retrieval_method" | "notes",
  string
> & { enabled: boolean; requires_js: boolean }

export const EMPTY_SOURCE_VALUES: SourceFormValues = {
  name: "",
  kind: "event_platform",
  tier: "2",
  base_url: "",
  retrieval_method: "manual",
  notes: "",
  enabled: true,
  requires_js: false,
}

export function sourceToFormValues(source: Source): SourceFormValues {
  return {
    name: source.name,
    kind: source.kind,
    tier: String(source.tier),
    base_url: source.base_url ?? "",
    retrieval_method: source.retrieval_method,
    notes: source.notes ?? "",
    enabled: source.enabled,
    requires_js: source.requires_js,
  }
}

export function readSourceForm(formData: FormData): SourceFormValues {
  const text = (name: string) => {
    const value = formData.get(name)
    return typeof value === "string" ? value : ""
  }
  return {
    name: text("name"),
    kind: text("kind"),
    tier: text("tier"),
    base_url: text("base_url"),
    retrieval_method: text("retrieval_method"),
    notes: text("notes"),
    // Checkboxes are only submitted when checked.
    enabled: formData.has("enabled"),
    requires_js: formData.has("requires_js"),
  }
}

function oneOf<T extends string | number>(value: T | string | number, options: readonly T[]): T | undefined {
  return options.find((option) => option === value)
}

/**
 * Full source body (create, and PATCH of every editable field). Enum values are checked
 * against the lists above; the API validates everything again.
 */
export function buildSourcePayload(values: SourceFormValues): {
  payload: SourceCreate
  fieldErrors: Record<string, string>
} {
  const fieldErrors: Record<string, string> = {}
  const kind = oneOf(values.kind, SOURCE_KINDS)
  const tier = oneOf(Number(values.tier), TIERS)
  const method = oneOf(values.retrieval_method, RETRIEVAL_METHODS)
  if (!kind) fieldErrors.kind = "Choose a kind."
  if (!tier) fieldErrors.tier = "Choose a tier."
  if (!method) fieldErrors.retrieval_method = "Choose a retrieval method."
  const payload: SourceCreate = {
    name: values.name.trim(),
    kind: kind ?? "manual",
    tier: tier ?? 4,
    base_url: values.base_url.trim() || null,
    retrieval_method: method ?? "manual",
    enabled: values.enabled,
    requires_js: values.requires_js,
    // Textareas submit CRLF line breaks; store LF.
    notes: values.notes.replace(/\r\n?/g, "\n").trim() || null,
  }
  return { payload, fieldErrors }
}
