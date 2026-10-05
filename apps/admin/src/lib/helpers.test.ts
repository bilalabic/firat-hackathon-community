import { describe, expect, it } from "vitest"

import type { ApiResult } from "@/lib/api/errors"
import type { LlmCheck, TelegramCheck } from "@/lib/api/types"

import { ACTION_META, needsDialog } from "./events"
import { formatAge, formatDateTime } from "./format"
import { llmHealth, telegramHealth } from "./health-levels"
import { hrefWith, lastPage, pageOffset, parsePage } from "./paging"
import { EMPTY_SOURCE_VALUES, buildSourcePayload } from "./sources"
import { safeHttpUrl } from "./urls"

describe("source payload", () => {
  it("normalizes CRLF notes and rejects unknown enum values", () => {
    const ok = buildSourcePayload({ ...EMPTY_SOURCE_VALUES, name: " ZZ ", notes: "a\r\nb\r\n" })
    expect(ok.fieldErrors).toEqual({})
    expect(ok.payload).toMatchObject({ name: "ZZ", notes: "a\nb", tier: 2, kind: "event_platform" })
    const bad = buildSourcePayload({ ...EMPTY_SOURCE_VALUES, kind: "x", tier: "9", retrieval_method: "ftp" })
    expect(Object.keys(bad.fieldErrors).sort()).toEqual(["kind", "retrieval_method", "tier"])
  })
})

describe("formatDateTime", () => {
  it("uses Europe/Istanbul regardless of the machine time zone", () => {
    expect(formatDateTime("2026-10-05T16:13:00Z")).toBe("5 Oct 2026, 19:13")
    expect(formatDateTime("2026-10-05T16:13:00Z", "UTC")).toBe("5 Oct 2026, 16:13")
    expect(formatDateTime("2026-10-05T16:13:00Z", "Not/AZone")).toBe("5 Oct 2026, 19:13")
  })
})

describe("event actions", () => {
  it("asks for confirmation or a reason exactly for the risky actions", () => {
    const dialogs = (Object.keys(ACTION_META) as (keyof typeof ACTION_META)[]).filter(needsDialog)
    expect(dialogs.sort()).toEqual(["archive", "publish", "reject", "request_changes", "unpublish"])
    expect(needsDialog("approve")).toBe(false)
    expect(ACTION_META.reject.reason).toBe("required")
  })
})

describe("formatAge", () => {
  const now = new Date("2026-10-05T12:00:00Z")
  it("formats minutes, hours and days", () => {
    expect(formatAge(null, now)).toBe("never")
    expect(formatAge("2026-10-05T11:30:00Z", now)).toBe("30 min ago")
    expect(formatAge("2026-10-04T12:00:00Z", now)).toBe("24 h ago")
    expect(formatAge("2026-10-01T12:00:00Z", now)).toBe("4 d ago")
  })
})

describe("health levels", () => {
  const ok = <T>(data: T): ApiResult<T> => ({ ok: true, data })
  const health = { provider: "ollama", configured_model: "qwen3.5:0.8b", installed_models: [], message: "" }

  it("maps every Ollama state", () => {
    expect(llmHealth(ok<LlmCheck>({ health: { ...health, status: "ok" }, test: { ok: true, latency_ms: 5 } })).level).toBe("ok")
    expect(llmHealth(ok<LlmCheck>({ health: { ...health, status: "ok" }, test: { ok: false, latency_ms: 5, error: "bad" } })).level).toBe("warn")
    expect(llmHealth(ok<LlmCheck>({ health: { ...health, status: "not_running" } })).text).toMatch(/^Not running/)
    expect(llmHealth(ok<LlmCheck>({ health: { ...health, status: "model_missing" } })).level).toBe("error")
  })

  it("maps Telegram states, including optional rights", () => {
    const base = { message: "m", missing_rights: [], missing_optional_rights: [] }
    expect(telegramHealth(ok<TelegramCheck>({ ...base, status: "not_configured" })).level).toBe("off")
    expect(telegramHealth(ok<TelegramCheck>({ ...base, status: "ok" })).level).toBe("ok")
    expect(telegramHealth(ok<TelegramCheck>({ ...base, status: "ok", missing_optional_rights: ["can_delete_messages"] })).level).toBe("warn")
    expect(telegramHealth(ok<TelegramCheck>({ ...base, status: "ok", excess_rights: ["can_promote_members"] })).level).toBe("warn")
    expect(telegramHealth(ok<TelegramCheck>({ ...base, status: "missing_rights", missing_rights: ["can_post_messages"] })).level).toBe("error")
    expect(telegramHealth(ok<TelegramCheck>({ ...base, status: "invalid_token" })).level).toBe("error")
  })

  it("reports 'not checked' when the API itself is down", () => {
    const down: ApiResult<LlmCheck> = { ok: false, error: { kind: "unreachable", status: null, message: "x", fieldErrors: {} } }
    expect(llmHealth(down).level).toBe("unknown")
  })
})

describe("paging and urls", () => {
  it("parses pages defensively", () => {
    expect(parsePage({ page: "3" })).toBe(3)
    expect(parsePage({ page: "-1" })).toBe(1)
    expect(parsePage({ page: "abc" })).toBe(1)
    expect(parsePage({ page: "10000" })).toBe(10000)
    expect(parsePage({ page: "10001" })).toBe(1)
    expect(parsePage({ page: "99999999999999999999" })).toBe(1)
    expect(parsePage({ page: "1e3" })).toBe(1)
    expect(lastPage(7, 25)).toBe(1)
    expect(lastPage(0, 25)).toBe(1)
    expect(lastPage(51, 25)).toBe(3)
    expect(pageOffset(3, 25)).toBe(50)
    expect(hrefWith("/events", { status: "draft", view: undefined, page: "" })).toBe("/events?status=draft")
  })

  it("links only http(s) URLs", () => {
    expect(safeHttpUrl("javascript:alert(1)")).toBeNull()
    expect(safeHttpUrl("not a url")).toBeNull()
    expect(safeHttpUrl("https://github.com/x")).toBe("https://github.com/x")
  })
})
