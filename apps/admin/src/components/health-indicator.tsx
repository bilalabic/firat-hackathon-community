import Link from "next/link"
import { cn } from "cn"

import { api } from "@/lib/api/client"
import { llmCheck, telegramCheck } from "@/lib/health"
import {
  apiHealth,
  dbHealth,
  llmHealth,
  telegramHealth,
  type HealthLevel,
  type HealthSummary,
} from "@/lib/health-levels"

const DOT: Record<HealthLevel, string> = {
  ok: "bg-emerald-500",
  warn: "bg-amber-500",
  error: "bg-destructive",
  off: "bg-muted-foreground/40",
  unknown: "border border-muted-foreground/60 bg-transparent",
}

export function StatusDot({ level, className }: { level: HealthLevel; className?: string }) {
  return <span aria-hidden className={cn("inline-block size-2 shrink-0 rounded-full", DOT[level], className)} />
}

type Item = { label: string } & HealthSummary

function Dots({ items }: { items: Item[] }) {
  const summary = items.map((item) => `${item.label}: ${item.text.replace(/\.$/, "")}`).join(". ")
  return (
    <Link
      href="/settings"
      aria-label={`System health. ${summary}. Open settings.`}
      className="flex items-center gap-3 rounded-md px-2 py-1 text-xs text-muted-foreground outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50"
    >
      {items.map((item) => (
        <span key={item.label} className="flex items-center gap-1.5" title={`${item.label}: ${item.text}`}>
          <StatusDot level={item.level} />
          <span className="hidden sm:inline">{item.label}</span>
        </span>
      ))}
    </Link>
  )
}

const LABELS = ["API", "DB", "Ollama", "Telegram"] as const

export function HealthIndicatorFallback() {
  return <Dots items={LABELS.map((label) => ({ label, level: "unknown", text: "Checking" }))} />
}

export async function HealthIndicator() {
  const [health, db, llm, telegram] = await Promise.all([
    api.health(),
    api.checkDatabase(),
    llmCheck.recent(),
    telegramCheck.recent(),
  ])
  // Ollama and Telegram results may be reused from earlier; never show them as current
  // while the API itself is down.
  const notChecked: HealthSummary = { level: "unknown", text: "Not checked (API not reachable)" }
  return (
    <Dots
      items={[
        { label: "API", ...apiHealth(health) },
        { label: "DB", ...dbHealth(db) },
        { label: "Ollama", ...(health.ok ? llmHealth(llm) : notChecked) },
        { label: "Telegram", ...(health.ok ? telegramHealth(telegram) : notChecked) },
      ]}
    />
  )
}
