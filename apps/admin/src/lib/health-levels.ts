// Maps check results to one traffic-light level and a short message. Pure; shared by
// the header indicator and the Settings page.

import type { ApiResult } from "@/lib/api/errors"
import type { AdminBotStatus, DbCheck, LlmCheck, TelegramCheck } from "@/lib/api/types"

/** ok = green, warn = amber, error = red, off = not configured (grey), unknown = not checked. */
export type HealthLevel = "ok" | "warn" | "error" | "off" | "unknown"

export type HealthSummary = { level: HealthLevel; text: string }

const NOT_CHECKED: HealthSummary = { level: "unknown", text: "Not checked (API not reachable)" }

function apiFailed(result: { ok: false; error: { kind: string; message: string } }): HealthSummary {
  return result.error.kind === "unreachable" ? NOT_CHECKED : { level: "error", text: result.error.message }
}

export function apiHealth(result: ApiResult<unknown>): HealthSummary {
  return result.ok ? { level: "ok", text: "Reachable" } : { level: "error", text: result.error.message }
}

export function dbHealth(result: ApiResult<DbCheck>): HealthSummary {
  if (!result.ok) return apiFailed(result)
  return result.data.ok
    ? { level: "ok", text: `OK (${result.data.latency_ms} ms)` }
    : { level: "error", text: "Query failed" }
}

export const LLM_STATUS_TEXT: Record<LlmCheck["health"]["status"], string> = {
  ok: "OK",
  not_running: "Not running",
  model_missing: "Model missing",
  error: "Error",
}

export function llmHealth(result: ApiResult<LlmCheck>): HealthSummary {
  if (!result.ok) return apiFailed(result)
  const { health, test } = result.data
  if (health.status !== "ok") {
    return { level: "error", text: `${LLM_STATUS_TEXT[health.status]}: ${health.message}` }
  }
  if (test && !test.ok) return { level: "warn", text: `Running, but the test call failed: ${test.error ?? "unknown error"}` }
  return { level: "ok", text: `OK (${health.configured_model})` }
}

export const TELEGRAM_STATUS_TEXT: Record<TelegramCheck["status"], string> = {
  ok: "OK",
  not_configured: "Not configured",
  invalid_token: "Invalid token",
  chat_not_found: "Channel not found",
  bot_not_admin: "Bot is not an admin",
  missing_rights: "Missing rights",
  error: "Error",
}

export function telegramHealth(result: ApiResult<TelegramCheck>): HealthSummary {
  if (!result.ok) return apiFailed(result)
  const { status, message, missing_optional_rights, excess_rights } = result.data
  const text = `${TELEGRAM_STATUS_TEXT[status]}: ${message}`
  if (status === "not_configured") return { level: "off", text }
  // Excess rights (least privilege) and missing optional rights do not block, but need attention.
  if (status === "ok") {
    return { level: missing_optional_rights?.length || excess_rights?.length ? "warn" : "ok", text }
  }
  return { level: "error", text }
}

export const ADMIN_BOT_STATE_TEXT: Record<AdminBotStatus["state"], string> = {
  disabled: "Disabled",
  config_error: "Configuration error",
  stopped: "Stopped",
  starting: "Starting",
  running: "Running",
  error: "Error, retrying",
}

export function adminBotHealth(result: ApiResult<AdminBotStatus>): HealthSummary {
  if (!result.ok) return apiFailed(result)
  const { state, config_error, last_error } = result.data
  const label = ADMIN_BOT_STATE_TEXT[state]
  if (state === "disabled") return { level: "off", text: label }
  if (state === "running") return { level: "ok", text: label }
  if (state === "starting") return { level: "unknown", text: label }
  const detail = config_error ?? last_error
  return { level: state === "stopped" ? "warn" : "error", text: detail ? `${label}: ${detail}` : label }
}
