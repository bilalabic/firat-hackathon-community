// Settings connection tests. Each check streams in on its own (Ollama can take
// a while on the first call after a model load).

import { ApiErrorState } from "@/components/api-error-state"
import { StatusDot } from "@/components/health-indicator"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { api } from "@/lib/api/client"
import { llmCheck, telegramCheck } from "@/lib/health"
import { formatDateTime } from "@/lib/format"
import {
  ADMIN_BOT_STATE_TEXT,
  LLM_STATUS_TEXT,
  TELEGRAM_STATUS_TEXT,
  adminBotHealth,
  dbHealth,
  llmHealth,
  telegramHealth,
  type HealthSummary,
} from "@/lib/health-levels"

function CheckCard({
  title,
  description,
  summary,
  children,
}: {
  title: string
  description: string
  summary?: HealthSummary & { label: string }
  children?: React.ReactNode
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          {summary && <StatusDot level={summary.level} className="size-2.5" />}
          {title}
          {summary && <span className="font-normal text-muted-foreground">— {summary.label}</span>}
        </CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      {children && <CardContent className="grid gap-3 text-sm">{children}</CardContent>}
    </Card>
  )
}

function Facts({ items }: { items: [string, React.ReactNode][] }) {
  return (
    <dl className="grid gap-x-4 gap-y-1 sm:grid-cols-[10rem_1fr]">
      {items.map(([label, value]) => (
        <div key={label} className="contents">
          <dt className="text-muted-foreground">{label}</dt>
          <dd className="break-words">{value}</dd>
        </div>
      ))}
    </dl>
  )
}

export function CheckFallback({ title, description }: { title: string; description: string }) {
  return (
    <CheckCard title={title} description={description}>
      <p role="status" className="text-muted-foreground">
        Running check…
      </p>
      <Skeleton className="h-12 w-full" />
    </CheckCard>
  )
}

export const DB_TEXT = { title: "Database", description: "GET /system/db: a query round-trip as the admin_backend role." }
export const LLM_TEXT = { title: "Ollama", description: "GET /llm/check: provider health plus one schema-constrained test generation." }
export const TELEGRAM_TEXT = { title: "Telegram", description: "GET /telegram/check: bot token, channel and the bot's admin rights." }

export async function DatabaseCheck() {
  const result = await api.checkDatabase()
  if (!result.ok && result.error.kind !== "unavailable") {
    return (
      <CheckCard {...DB_TEXT}>
        <ApiErrorState error={result.error} />
      </CheckCard>
    )
  }
  const summary = dbHealth(result)
  return (
    <CheckCard {...DB_TEXT} summary={{ ...summary, label: result.ok ? "OK" : "Unavailable" }}>
      {result.ok ? (
        <Facts
          items={[
            ["Latency", `${result.data.latency_ms} ms`],
            ["Role", result.data.role],
            ["Server version", result.data.server_version],
          ]}
        />
      ) : (
        <p>{result.error.message}</p>
      )}
    </CheckCard>
  )
}

export async function OllamaCheck() {
  const result = await llmCheck.fresh()
  if (!result.ok) {
    return (
      <CheckCard {...LLM_TEXT}>
        <ApiErrorState error={result.error} />
      </CheckCard>
    )
  }
  const { health, test } = result.data
  const summary = llmHealth(result)
  return (
    <CheckCard {...LLM_TEXT} summary={{ ...summary, label: LLM_STATUS_TEXT[health.status] }}>
      <p>{health.message}</p>
      <Facts
        items={[
          ["Provider", health.provider],
          ["Configured model", health.configured_model],
          ["Installed models", (health.installed_models ?? []).join(", ") || "—"],
        ]}
      />
      {test ? (
        <div className="grid gap-2 rounded-lg border p-3">
          <div className="font-medium">
            Test generation: {test.ok ? "OK" : "Failed"} in {test.latency_ms} ms
          </div>
          {test.output && (
            <pre className="overflow-x-auto rounded-md bg-muted p-2 font-mono text-xs">
              {JSON.stringify(test.output, null, 2)}
            </pre>
          )}
          {test.error && <p className="text-destructive">{test.error}</p>}
        </div>
      ) : (
        <p className="text-muted-foreground">The test generation runs only when the provider is OK.</p>
      )}
    </CheckCard>
  )
}

export async function TelegramCheck() {
  const result = await telegramCheck.fresh()
  if (!result.ok) {
    return (
      <CheckCard {...TELEGRAM_TEXT}>
        <ApiErrorState error={result.error} />
      </CheckCard>
    )
  }
  const data = result.data
  const summary = telegramHealth(result)
  return (
    <CheckCard {...TELEGRAM_TEXT} summary={{ ...summary, label: TELEGRAM_STATUS_TEXT[data.status] }}>
      <p>{data.message}</p>
      {data.status !== "not_configured" && (
        <Facts
          items={[
            ["Bot", data.bot_username ? `@${data.bot_username}` : "—"],
            ["Channel", data.chat_title ?? "—"],
            ["Chat type", data.chat_type ?? "—"],
            ["Missing rights", (data.missing_rights ?? []).join(", ") || "None"],
            ["Missing optional rights", (data.missing_optional_rights ?? []).join(", ") || "None"],
            ["Unneeded rights granted", (data.excess_rights ?? []).join(", ") || "None"],
          ]}
        />
      )}
    </CheckCard>
  )
}

export const ADMIN_BOT_TEXT = {
  title: "Telegram admin bot",
  description: "GET /admin-bot/status: review and application decisions from Telegram (separate admin bot).",
}

export async function AdminBotCheck() {
  const result = await api.adminBotStatus()
  if (!result.ok) {
    return (
      <CheckCard {...ADMIN_BOT_TEXT}>
        <ApiErrorState error={result.error} />
      </CheckCard>
    )
  }
  const data = result.data
  const summary = adminBotHealth(result)
  const count = (value: number | null | undefined) => (value == null ? "—" : String(value))
  return (
    <CheckCard {...ADMIN_BOT_TEXT} summary={{ ...summary, label: ADMIN_BOT_STATE_TEXT[data.state] }}>
      {data.state === "disabled" ? (
        <p className="text-muted-foreground">
          Set TELEGRAM_ADMIN_ENABLED=true, TELEGRAM_ADMIN_BOT_TOKEN and TELEGRAM_ADMIN_USER_IDS in
          services/api/.env and restart the API.
        </p>
      ) : (
        <>
          {data.config_error && <p className="text-destructive">{data.config_error}</p>}
          {data.last_error && (
            <p className={data.state === "error" ? "text-destructive" : "text-muted-foreground"}>
              Last error ({formatDateTime(data.last_error_at)}): {data.last_error}
            </p>
          )}
          <Facts
            items={[
              ["Bot", data.bot_username ? `@${data.bot_username}` : "—"],
              ["Allowed admins", String(data.allowlist_size)],
              ["Last poll", formatDateTime(data.last_poll_at)],
              ["Last scan", formatDateTime(data.last_scan_at)],
              ["Awaiting decision", count(data.pending_notifications)],
              ["Open reason prompts", count(data.pending_replies)],
              [
                "Button age limit",
                data.max_press_age_hours == null ? "—" : `${data.max_press_age_hours} h`,
              ],
            ]}
          />
        </>
      )}
    </CheckCard>
  )
}

export function RevalidationCheck() {
  return (
    <CheckCard
      title="Web revalidation"
      description="Whether the API can ask the public site to revalidate after publish, unpublish and edits."
      summary={{ level: "unknown", text: "Not reported", label: "Not reported by the API" }}
    >
      <p>
        The API does not expose whether WEB_BASE_URL and WEB_REVALIDATE_SECRET are set. Its startup
        log says “web revalidation enabled” or “web revalidation disabled”.
      </p>
    </CheckCard>
  )
}
