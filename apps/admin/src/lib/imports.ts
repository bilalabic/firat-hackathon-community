// URL import (V1.2): input check, labels and evidence display helpers. Pure (no
// server-only import) so it can be unit tested and used by Client Components.

import type {
  Evidence,
  EvidenceSource,
  FieldEvidence,
  FlagKind,
  ImportRun,
} from "@/lib/api/types"

export const URL_MAX_LENGTH = 500

export const SOURCE_LABELS: Record<EvidenceSource, string> = {
  jsonld: "JSON-LD",
  meta: "Meta",
  llm: "LLM",
  manual: "Manual",
}

export const SOURCE_HINTS: Record<EvidenceSource, string> = {
  jsonld: "Structured data (schema.org Event) on the page",
  meta: "Page title or meta tags",
  llm: "Proposed by the local LLM; the snippet was found in the page text",
  manual: "Entered by an admin",
}

export const FLAG_LABELS: Record<FlagKind, string> = {
  unsupported: "Unsupported",
  conflict: "Conflict",
  rule_violation: "Rule violation",
  invalid: "Invalid",
}

export const FLAG_HINTS: Record<FlagKind, string> = {
  unsupported: "The LLM's snippet does not occur in the page: the value was dropped.",
  conflict: "Structured data and the LLM disagree: the structured value was kept.",
  rule_violation: "The value breaks an event rule (e.g. dates out of order): it was dropped.",
  invalid: "The value does not pass the event field rules: it was dropped.",
}

export const FIELD_LABELS: Record<string, string> = {
  title: "Title",
  organizer: "Organizer",
  summary: "Summary",
  format: "Format",
  city: "City",
  country: "Country",
  venue: "Venue",
  start_date: "Start",
  end_date: "End",
  application_deadline: "Application deadline",
  eligibility: "Eligibility",
  team_min: "Team min",
  team_max: "Team max",
  prize_pool: "Prize pool",
  currency: "Currency",
  is_free: "Free",
  application_url: "Application URL",
}

export function fieldLabel(field: string): string {
  return FIELD_LABELS[field] ?? field.replace(/_/g, " ").replace(/^./, (ch) => ch.toUpperCase())
}

export function displayValue(field: string, value: string | null): string {
  if (value === null) return "—"
  if (field === "is_free") return value === "true" ? "Yes" : value === "false" ? "No" : value
  if (field === "format") return value.replace(/_/g, " ").replace(/^./, (ch) => ch.toUpperCase())
  return value
}

/** Client-side check before the request (the API validates again). */
export function parseImportUrl(raw: string): { url: string } | { error: string } {
  const url = raw.trim()
  if (!url) return { error: "Enter the event page URL." }
  if (url.length > URL_MAX_LENGTH) return { error: `The URL must be at most ${URL_MAX_LENGTH} characters.` }
  let parsed: URL
  try {
    parsed = new URL(url)
  } catch {
    return { error: "Enter a full URL, starting with https:// or http://." }
  }
  if (parsed.protocol !== "https:" && parsed.protocol !== "http:") {
    return { error: "Only http and https URLs can be imported." }
  }
  if (parsed.username || parsed.password) return { error: "The URL must not contain credentials." }
  return { url }
}

export type EvidenceSummary = {
  proposed: number
  flagged: number
  flags: Partial<Record<FlagKind, number>>
  editedSinceImport: number
}

export function summarizeEvidence(fields: FieldEvidence[]): EvidenceSummary {
  const flags: Partial<Record<FlagKind, number>> = {}
  for (const field of fields) {
    for (const flag of field.flags) flags[flag.kind] = (flags[flag.kind] ?? 0) + 1
  }
  return {
    proposed: fields.filter((field) => field.value_text !== null).length,
    flagged: fields.filter((field) => field.flags.length > 0).length,
    flags,
    editedSinceImport: fields.filter((field) => field.matches_current === false).length,
  }
}

function statString(run: ImportRun | null | undefined, key: string): string | null {
  const value = run?.stats?.[key]
  return typeof value === "string" && value ? value : null
}

function statNumber(run: ImportRun | null | undefined, key: string): number | null {
  const value = run?.stats?.[key]
  return typeof value === "number" && Number.isFinite(value) ? value : null
}

/** What the run stats say about the extraction, for the evidence card header. */
export function runDetails(evidence: Evidence): {
  extractedBy: string | null
  llmError: string | null
  finalUrl: string | null
  imageUrl: string | null
  seconds: number | null
} {
  const total = statNumber(evidence.run, "total_ms")
  return {
    extractedBy: statString(evidence.run, "extracted_by"),
    llmError: statString(evidence.run, "llm_error"),
    finalUrl: statString(evidence.run, "final_url"),
    imageUrl: statString(evidence.run, "image_url"),
    seconds: total === null ? null : Math.round(total / 100) / 10,
  }
}

export const RUN_STATUS_LABELS: Record<ImportRun["status"], string> = {
  running: "Running",
  succeeded: "Succeeded",
  failed: "Failed",
}

/** A run still `running` after this long was interrupted (API restart, crash). */
export const STALE_RUN_MS = 10 * 60_000

export function runState(run: ImportRun, now: Date = new Date()): "running" | "interrupted" | "succeeded" | "duplicate" | "failed" {
  if (run.status === "running") {
    return now.getTime() - new Date(run.started_at).getTime() > STALE_RUN_MS ? "interrupted" : "running"
  }
  if (run.status === "succeeded" && run.stats?.outcome === "duplicate") return "duplicate"
  return run.status
}
