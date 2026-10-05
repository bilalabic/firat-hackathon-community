import { describe, expect, it } from "vitest"

import type { ApiResult } from "@/lib/api/errors"
import type { LlmCheck, TelegramCheck } from "@/lib/api/types"

import { ACTION_META, needsDialog } from "./events"
import { formatAge } from "./format"
import { llmHealth, telegramHealth } from "./health-levels"
import { hrefWith, pageOffset, parsePage } from "./paging"
import { safeHttpUrl } from "./urls"

describe("event actions", () => {
  it("asks for confirmation or a reason exactly for the risky actions", () => {
    const dialogs = (Object.keys(ACTION_META) as (keyof typeof ACTION_META)[]).filter(needsDialog)
    expect(dialogs.sort()).toEqual(["archive", "reject", "request_changes", "unpublish"])
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
    expect(telegramHealth(ok<TelegramCheck>({ ...base, status: "missing_rights", missing_rights: ["can_post_messages"] })).level).toBe("error")
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
    expect(pageOffset(3, 25)).toBe(50)
    expect(hrefWith("/events", { status: "draft", view: undefined, page: "" })).toBe("/events?status=draft")
  })

  it("links only http(s) URLs", () => {
    expect(safeHttpUrl("javascript:alert(1)")).toBeNull()
    expect(safeHttpUrl("not a url")).toBeNull()
    expect(safeHttpUrl("https://github.com/x")).toBe("https://github.com/x")
  })
})
