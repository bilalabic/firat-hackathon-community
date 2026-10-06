// Server-only client for the FastAPI admin API. The bearer token is read here and
// never leaves the server: Server Components and Server Actions call these functions,
// the browser never talks to the API.
//
// Every call returns an ApiResult instead of throwing, so pages can render a clear
// state (e.g. "API not reachable") rather than an error boundary. Request and response
// bodies are never logged: some contain personal data (applications).

import "server-only"

import { connection } from "next/server"

import {
  configError,
  parseErrorResponse,
  timeoutError,
  unreachableError,
  type ApiResult,
} from "./errors"
import type { operations } from "./schema"

type Ops = operations
type OpName = keyof Ops

type JsonContent<R> = R extends { content: { "application/json": infer B } } ? B : null
type Responses<K extends OpName> = Ops[K]["responses"]
type SuccessBody<K extends OpName> =
  Responses<K> extends { 200: infer R }
    ? JsonContent<R>
    : Responses<K> extends { 201: infer R }
      ? JsonContent<R>
      : null
type RequestBody<K extends OpName> = Ops[K] extends {
  requestBody: { content: { "application/json": infer B } }
}
  ? B
  : never
type Query<K extends OpName> = NonNullable<Ops[K]["parameters"]["query"]>

type QueryValue = string | number | boolean | null | undefined | readonly (string | number)[]

const DEFAULT_API_URL = "http://127.0.0.1:8000"
const DEFAULT_TIMEOUT_MS = 15_000

function apiBaseUrl(): string {
  return (process.env.ADMIN_API_URL || DEFAULT_API_URL).replace(/\/+$/, "")
}

function buildQuery(query: Record<string, QueryValue> | undefined): string {
  if (!query) return ""
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null) continue
    if (Array.isArray(value)) value.forEach((item) => params.append(key, String(item)))
    else params.set(key, String(value))
  }
  const text = params.toString()
  return text ? `?${text}` : ""
}

/** Path segment from an id; ids are validated by callers, this only guarantees one segment. */
const seg = (id: string) => encodeURIComponent(id)

async function request<K extends OpName>(
  _operation: K,
  method: "GET" | "POST" | "PATCH" | "DELETE",
  path: string,
  options: {
    query?: Query<K>
    body?: RequestBody<K>
    timeoutMs?: number
  } = {}
): Promise<ApiResult<SuccessBody<K>>> {
  // Every API read is per request: never prerender or cache it.
  await connection()

  const token = process.env.ADMIN_API_TOKEN
  if (!token) {
    return {
      ok: false,
      error: configError("ADMIN_API_TOKEN is not set. Add it to apps/admin/.env.local and restart the admin."),
    }
  }

  const baseUrl = apiBaseUrl()
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS
  const headers: Record<string, string> = {
    Accept: "application/json",
    Authorization: `Bearer ${token}`,
  }
  if (options.body !== undefined) headers["Content-Type"] = "application/json"

  let response: Response
  try {
    response = await fetch(
      `${baseUrl}${path}${buildQuery(options.query as Record<string, QueryValue> | undefined)}`,
      {
        method,
        headers,
        body: options.body === undefined ? undefined : JSON.stringify(options.body),
        cache: "no-store",
        redirect: "error",
        signal: AbortSignal.timeout(timeoutMs),
      }
    )
  } catch (error) {
    if (error instanceof DOMException && error.name === "TimeoutError") {
      return { ok: false, error: timeoutError(Math.round(timeoutMs / 1000)) }
    }
    return { ok: false, error: unreachableError(baseUrl) }
  }

  const body: unknown =
    response.status === 204 ? null : await response.json().catch(() => null)
  if (!response.ok) {
    return { ok: false, error: parseErrorResponse(response.status, body) }
  }
  return { ok: true, data: body as SuccessBody<K> }
}

export const api = {
  health: () => request("health", "GET", "/health", { timeoutMs: 5_000 }),
  overview: () => request("get_overview", "GET", "/overview"),

  listEvents: (query: Query<"list_events">) =>
    request("list_events", "GET", "/events", { query }),
  getEvent: (id: string) => request("get_event", "GET", `/events/${seg(id)}`),
  createEvent: (body: RequestBody<"create_event">) =>
    request("create_event", "POST", "/events", { body }),
  updateEvent: (id: string, body: RequestBody<"update_event">) =>
    request("update_event", "PATCH", `/events/${seg(id)}`, { body }),
  transitionEvent: (id: string, body: RequestBody<"transition_event">) =>
    request("transition_event", "POST", `/events/${seg(id)}/transitions`, { body }),
  // The official-URL check fetches the site (10 s per hop, up to 5 redirects).
  getReview: (id: string) =>
    request("get_event_review", "GET", `/events/${seg(id)}/review`, { timeoutMs: 70_000 }),

  listEventSources: (eventId: string) =>
    request("list_event_sources", "GET", `/events/${seg(eventId)}/sources`),
  addEventSource: (eventId: string, body: RequestBody<"add_event_source">) =>
    request("add_event_source", "POST", `/events/${seg(eventId)}/sources`, { body }),
  removeEventSource: (eventId: string, eventSourceId: string) =>
    request(
      "remove_event_source",
      "DELETE",
      `/events/${seg(eventId)}/sources/${seg(eventSourceId)}`
    ),

  listSources: () => request("list_sources", "GET", "/sources"),
  createSource: (body: RequestBody<"create_source">) =>
    request("create_source", "POST", "/sources", { body }),
  updateSource: (id: string, body: RequestBody<"update_source">) =>
    request("update_source", "PATCH", `/sources/${seg(id)}`, { body }),

  listCommunityApplications: (query: Query<"list_community_applications">) =>
    request("list_community_applications", "GET", "/community-applications", { query }),
  updateCommunityApplication: (id: string, body: RequestBody<"update_community_application">) =>
    request("update_community_application", "PATCH", `/community-applications/${seg(id)}`, {
      body,
    }),
  listTeamApplications: (query: Query<"list_team_applications">) =>
    request("list_team_applications", "GET", "/team-applications", { query }),
  updateTeamApplication: (id: string, body: RequestBody<"update_team_application">) =>
    request("update_team_application", "PATCH", `/team-applications/${seg(id)}`, { body }),

  checkDatabase: () => request("check_database", "GET", "/system/db"),
  // OLLAMA_TIMEOUT_S defaults to 120 s; the first call after a model load is slow.
  checkLlm: () => request("llm_check", "GET", "/llm/check", { timeoutMs: 150_000 }),
  checkTelegram: () => request("telegram_check", "GET", "/telegram/check", { timeoutMs: 45_000 }),
  // Reads in-process state plus two counts; no Telegram call.
  adminBotStatus: () => request("admin_bot_status", "GET", "/admin-bot/status"),
}
