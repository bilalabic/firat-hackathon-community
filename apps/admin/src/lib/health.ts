// Checks for the header health indicator. API and DB are cheap and run on every page;
// the Ollama check makes a test generation and the Telegram check calls the Bot API,
// so their last results are reused for a few minutes. The Settings page always runs
// them fresh and refreshes this memo. In-process only (single local admin).

import "server-only"

import { api } from "@/lib/api/client"
import type { ApiResult } from "@/lib/api/errors"
import type { LlmCheck, TelegramCheck } from "@/lib/api/types"

const REUSE_MS = 5 * 60_000

type Entry<T> = { at: number; result: Promise<ApiResult<T>> }

function memo<T>(run: () => Promise<ApiResult<T>>) {
  let entry: Entry<T> | null = null
  const fresh = () => {
    const result = run()
    entry = { at: Date.now(), result }
    // A failed check is not reused: the next page view retries it.
    void result.then((value) => {
      if (!value.ok && entry?.result === result) entry = null
    })
    return result
  }
  return {
    fresh,
    recent: () => (entry && Date.now() - entry.at < REUSE_MS ? entry.result : fresh()),
  }
}

export const llmCheck = memo<LlmCheck>(api.checkLlm)
export const telegramCheck = memo<TelegramCheck>(api.checkTelegram)
