import { Suspense } from "react"

import {
  CheckFallback,
  DB_TEXT,
  DatabaseCheck,
  LLM_TEXT,
  OllamaCheck,
  RevalidationCheck,
  TELEGRAM_TEXT,
  TelegramCheck,
} from "@/components/connection-checks"
import { PageBody, Section } from "@/components/page-body"
import { RerunButton } from "@/components/rerun-button"
import { SiteHeader } from "@/components/site-header"

export default function SettingsPage() {
  return (
    <>
      <SiteHeader title="Settings" />
      <PageBody>
        <Section className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-sm text-muted-foreground">
            Connection tests run through the API every time this page loads.
          </p>
          <RerunButton />
        </Section>
        <Section className="grid items-start gap-4 @4xl/main:grid-cols-2">
          <Suspense fallback={<CheckFallback {...DB_TEXT} />}>
            <DatabaseCheck />
          </Suspense>
          <Suspense fallback={<CheckFallback {...LLM_TEXT} />}>
            <OllamaCheck />
          </Suspense>
          <Suspense fallback={<CheckFallback {...TELEGRAM_TEXT} />}>
            <TelegramCheck />
          </Suspense>
          <RevalidationCheck />
        </Section>
      </PageBody>
    </>
  )
}
