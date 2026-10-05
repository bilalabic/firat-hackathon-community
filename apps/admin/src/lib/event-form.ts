// Event form <-> API payload. Pure functions (unit tested). The API is the authority
// for validation; this layer only converts form strings to JSON types and catches
// input that cannot be converted (e.g. "abc" for a team size).

import type { Event, EventCreate, EventUpdate } from "@/lib/api/types"

export type FormValues = Record<string, string>

type FieldKind = "text" | "textarea" | "url" | "date" | "integer" | "decimal" | "tags" | "select" | "boolean"

export type FieldOption = { value: string; label: string }

export type EventField = {
  name: keyof EventUpdate & string
  label: string
  kind: FieldKind
  /** Cannot be empty (the API rejects null). */
  required?: boolean
  /** Needed before the event can be submitted for review. */
  requiredForReview?: boolean
  maxLength?: number
  options?: FieldOption[]
  placeholder?: string
  hint?: string
}

export const DEFAULT_TIMEZONE = "Europe/Istanbul"

const FORMAT_OPTIONS: FieldOption[] = [
  { value: "", label: "Not set" },
  { value: "in_person", label: "In person" },
  { value: "online", label: "Online" },
  { value: "hybrid", label: "Hybrid" },
]

const VERIFICATION_OPTIONS: FieldOption[] = [
  { value: "unverified", label: "Unverified" },
  { value: "partially_verified", label: "Partially verified" },
  { value: "verified", label: "Verified" },
]

const BOOLEAN_OPTIONS: FieldOption[] = [
  { value: "", label: "Unknown" },
  { value: "true", label: "Yes" },
  { value: "false", label: "No" },
]

export const EVENT_FIELD_GROUPS: { title: string; fields: EventField[] }[] = [
  {
    title: "Basics",
    fields: [
      { name: "title", label: "Title", kind: "text", required: true, maxLength: 160 },
      { name: "organizer", label: "Organizer", kind: "text", maxLength: 160 },
      { name: "summary", label: "Summary", kind: "textarea", requiredForReview: true, maxLength: 300 },
      { name: "description", label: "Description", kind: "textarea", maxLength: 5000 },
    ],
  },
  {
    title: "Classification",
    fields: [
      { name: "format", label: "Format", kind: "select", requiredForReview: true, options: FORMAT_OPTIONS },
      { name: "verification_status", label: "Verification", kind: "select", required: true, options: VERIFICATION_OPTIONS },
      { name: "categories", label: "Categories", kind: "tags", hint: "Comma-separated, e.g. ai, web3", placeholder: "ai, health" },
      { name: "technologies", label: "Technologies", kind: "tags", hint: "Comma-separated", placeholder: "python, react" },
    ],
  },
  {
    title: "Dates and place",
    fields: [
      { name: "start_date", label: "Start date", kind: "date", requiredForReview: true },
      { name: "end_date", label: "End date", kind: "date" },
      { name: "application_deadline", label: "Application deadline", kind: "date" },
      { name: "timezone", label: "Timezone", kind: "text", required: true, hint: "IANA name, e.g. Europe/Istanbul" },
      { name: "city", label: "City", kind: "text", maxLength: 120 },
      { name: "country", label: "Country", kind: "text", hint: "ISO 3166-1 alpha-2, e.g. TR", maxLength: 2 },
      { name: "venue", label: "Venue", kind: "text", maxLength: 200 },
    ],
  },
  {
    title: "Participation",
    fields: [
      { name: "eligibility", label: "Eligibility", kind: "textarea", maxLength: 500 },
      { name: "team_min", label: "Team size (min)", kind: "integer", hint: "1-20" },
      { name: "team_max", label: "Team size (max)", kind: "integer", hint: "1-20" },
      { name: "is_free", label: "Free to join", kind: "boolean", options: BOOLEAN_OPTIONS },
      { name: "prize_pool", label: "Prize pool", kind: "decimal", hint: "Requires a currency" },
      { name: "currency", label: "Currency", kind: "text", hint: "ISO 4217, e.g. TRY", maxLength: 3 },
    ],
  },
  {
    title: "Links",
    fields: [
      { name: "official_url", label: "Official URL", kind: "url", required: true, maxLength: 500 },
      { name: "application_url", label: "Application URL", kind: "url", maxLength: 500 },
      { name: "poster_url", label: "Poster URL", kind: "url", hint: "https only", maxLength: 500 },
      { name: "banner_url", label: "Banner URL", kind: "url", hint: "https only", maxLength: 500 },
      { name: "organizer_logo_url", label: "Organizer logo URL", kind: "url", hint: "https only", maxLength: 500 },
    ],
  },
  {
    title: "Internal",
    fields: [{ name: "internal_notes", label: "Internal notes", kind: "textarea", maxLength: 5000, hint: "Never shown publicly. Reject and request-changes reasons are appended here." }],
  },
]

export const EVENT_FIELDS: EventField[] = EVENT_FIELD_GROUPS.flatMap((group) => group.fields)

export const EMPTY_EVENT_VALUES: FormValues = {
  ...Object.fromEntries(EVENT_FIELDS.map((field) => [field.name, ""])),
  timezone: DEFAULT_TIMEZONE,
  verification_status: "unverified",
}

/** Form strings for an existing event (the edit form's initial values). */
export function eventToFormValues(event: Event): FormValues {
  const values: FormValues = {}
  for (const field of EVENT_FIELDS) {
    const value = event[field.name as keyof Event]
    if (value === null || value === undefined) values[field.name] = ""
    else if (Array.isArray(value)) values[field.name] = value.join(", ")
    else values[field.name] = String(value)
  }
  return values
}

/** Reads exactly the event fields from submitted form data. */
export function readEventForm(formData: FormData): FormValues {
  const values: FormValues = {}
  for (const field of EVENT_FIELDS) {
    const raw = formData.get(field.name)
    values[field.name] = typeof raw === "string" ? raw : ""
  }
  return values
}

type PayloadValue = string | number | boolean | string[] | null
export type EventPayload = Record<string, PayloadValue>

function parseTags(text: string): string[] {
  const tags = text
    .split(/[,\n]/)
    .map((tag) => tag.trim().toLowerCase())
    .filter(Boolean)
  return [...new Set(tags)]
}

/**
 * Converts form strings to API JSON. Empty optional fields become null (clears them on
 * PATCH). Required text fields are sent as typed, so the API reports them per field.
 */
export function buildEventPayload(values: FormValues): {
  payload: EventPayload
  fieldErrors: Record<string, string>
} {
  const payload: EventPayload = {}
  const fieldErrors: Record<string, string> = {}

  for (const field of EVENT_FIELDS) {
    const text = (values[field.name] ?? "").trim()
    switch (field.kind) {
      case "tags":
        payload[field.name] = parseTags(text)
        break
      case "integer":
        if (text === "") payload[field.name] = null
        else if (/^\d+$/.test(text)) payload[field.name] = Number(text)
        else fieldErrors[field.name] = "Enter a whole number."
        break
      case "decimal":
        if (text === "") payload[field.name] = null
        else if (/^\d+(\.\d{1,2})?$/.test(text)) payload[field.name] = text
        else fieldErrors[field.name] = "Enter an amount such as 5000 or 5000.50."
        break
      case "boolean":
        payload[field.name] = text === "" ? null : text === "true"
        break
      default:
        if (field.name === "country" || field.name === "currency") {
          payload[field.name] = text === "" ? null : text.toUpperCase()
        } else {
          payload[field.name] = text === "" && !field.required ? null : text
        }
    }
  }
  return { payload, fieldErrors }
}

function sameValue(next: PayloadValue, current: unknown): boolean {
  if (Array.isArray(next)) {
    return Array.isArray(current) && next.join("\u0000") === current.join("\u0000")
  }
  if (next === null || current === null || current === undefined) {
    return next === null && (current === null || current === undefined)
  }
  // prize_pool comes back as "5000.00" (Decimal) while the form may send "5000".
  if (typeof next === "string" && /^\d+(\.\d+)?$/.test(next) && typeof current === "string") {
    return Number(next) === Number(current)
  }
  return next === current
}

/** Only the fields that differ from the current event (PATCH body). */
export function changedFields(payload: EventPayload, current: Event): EventPayload {
  const changes: EventPayload = {}
  for (const [name, value] of Object.entries(payload)) {
    if (!sameValue(value, current[name as keyof Event])) changes[name] = value
  }
  return changes
}

// The payload is built from EVENT_FIELDS, whose names are EventUpdate keys and whose
// kinds produce the matching JSON types; the API validates every value again.
export const asEventCreate = (payload: EventPayload) => payload as unknown as EventCreate
export const asEventUpdate = (payload: EventPayload) => payload as unknown as EventUpdate
