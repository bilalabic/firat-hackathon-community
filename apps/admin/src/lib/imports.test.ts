import { describe, expect, it } from "vitest"

import type { Evidence, FieldEvidence, ImportRun } from "@/lib/api/types"

import {
  STALE_RUN_MS,
  displayValue,
  fieldLabel,
  parseImportUrl,
  runDetails,
  runState,
  summarizeEvidence,
} from "./imports"

const RUN: ImportRun = {
  id: "00000000-0000-4000-8000-000000000001",
  kind: "url_import",
  status: "succeeded",
  url: "https://example.com/hackathon",
  event_id: "00000000-0000-4000-8000-000000000002",
  error: null,
  stats: { outcome: "created", total_ms: 12_345, extracted_by: "llm:qwen", llm_error: null },
  started_at: "2026-10-11T09:00:00Z",
  finished_at: "2026-10-11T09:00:12Z",
}

function field(overrides: Partial<FieldEvidence>): FieldEvidence {
  return {
    field: "city",
    value_text: "Elazığ",
    source: "llm",
    extracted_by: "llm:qwen",
    snippet: "Elazığ'da",
    flags: [],
    matches_current: true,
    ...overrides,
  }
}

describe("parseImportUrl", () => {
  it("accepts http(s) URLs and trims them", () => {
    expect(parseImportUrl("  https://example.com/x  ")).toEqual({ url: "https://example.com/x" })
    expect(parseImportUrl("http://example.com")).toEqual({ url: "http://example.com" })
  })

  it("rejects empty, relative, non-http and credential URLs", () => {
    for (const raw of ["", "   ", "example.com/x", "ftp://example.com", "javascript:alert(1)", "https://u:p@example.com"]) {
      expect(parseImportUrl(raw)).toHaveProperty("error")
    }
    expect(parseImportUrl(`https://example.com/${"x".repeat(500)}`)).toHaveProperty("error")
  })
})

describe("evidence display", () => {
  it("labels fields and formats values", () => {
    expect(fieldLabel("application_deadline")).toBe("Application deadline")
    expect(fieldLabel("some_new_field")).toBe("Some new field")
    expect(displayValue("is_free", "true")).toBe("Yes")
    expect(displayValue("format", "in_person")).toBe("In person")
    expect(displayValue("city", null)).toBe("—")
  })

  it("summarizes proposed values, flags and later edits", () => {
    const summary = summarizeEvidence([
      field({}),
      field({ field: "start_date", flags: [{ kind: "conflict", detail: "x" }], matches_current: false }),
      field({
        field: "organizer",
        value_text: null,
        source: null,
        matches_current: null,
        flags: [
          { kind: "unsupported", detail: "x" },
          { kind: "conflict", detail: "y" },
        ],
      }),
    ])
    expect(summary).toEqual({
      proposed: 2,
      flagged: 2,
      flags: { conflict: 2, unsupported: 1 },
      editedSinceImport: 1,
    })
  })

  it("reads run stats defensively", () => {
    const evidence: Evidence = { event_id: RUN.event_id!, run: RUN, extracted_at: RUN.finished_at, fields: [] }
    expect(runDetails(evidence)).toEqual({
      extractedBy: "llm:qwen",
      llmError: null,
      finalUrl: null,
      imageUrl: null,
      seconds: 12.3,
    })
    const odd: Evidence = { ...evidence, run: { ...RUN, stats: { total_ms: "slow", llm_error: 5 } } }
    expect(runDetails(odd)).toMatchObject({ seconds: null, llmError: null })
    expect(runDetails({ ...evidence, run: null }).extractedBy).toBeNull()
  })
})

describe("runState", () => {
  const now = new Date("2026-10-11T09:05:00Z")

  it("tells duplicates, fresh and interrupted runs apart", () => {
    expect(runState(RUN, now)).toBe("succeeded")
    expect(runState({ ...RUN, stats: { outcome: "duplicate" } }, now)).toBe("duplicate")
    expect(runState({ ...RUN, status: "failed", error: "x" }, now)).toBe("failed")
    const running = { ...RUN, status: "running" as const, finished_at: null }
    expect(runState(running, now)).toBe("running")
    expect(runState(running, new Date(now.getTime() + STALE_RUN_MS))).toBe("interrupted")
  })
})
