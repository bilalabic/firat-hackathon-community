"use server"

// Telegram channel post actions (V1.1a). Server Actions are reachable by direct POST, so
// every input is validated here before it is sent to the API (which validates again).
// Send and Update carry the `content_hash` of the preview the operator confirmed: if the
// event changed since, the API refuses with 409 instead of posting unseen text.

import { refresh } from "next/cache"
import { z } from "zod"

import { api } from "@/lib/api/client"
import type { ApiResult } from "@/lib/api/errors"
import type { ChannelActionOut } from "@/lib/api/types"
import { MAY_HAVE_APPLIED, type ChannelActionResult } from "@/lib/channel"

const uuid = z.uuid()
const contentHash = z.string().regex(/^[0-9a-f]{64}$/)

const postInput = z.object({ eventId: uuid, contentHash })
const publicationInput = z.object({ eventId: uuid, publicationId: uuid })

const INVALID: ChannelActionResult = { ok: false, kind: "invalid", message: "Invalid channel post request." }

function settle(
  result: ApiResult<ChannelActionOut>,
  { postsToTelegram = false }: { postsToTelegram?: boolean } = {}
): ChannelActionResult {
  // Re-render on every outcome: a failed write may still have changed what the page shows
  // (a 502 records the attempt, a 409 means the page was stale, and after a timeout or a
  // dropped connection the API usually finishes the write anyway).
  refresh()
  if (result.ok) return { ok: true, message: result.data.message }
  const { kind, message } = result.error
  // Aborting the request does not stop the API handler, which usually posts anyway.
  const ambiguous = postsToTelegram && (kind === "timeout" || kind === "unreachable")
  return { ok: false, kind, message: ambiguous ? `${message} ${MAY_HAVE_APPLIED}` : message }
}

export async function sendChannelPost(input: { eventId: string; contentHash: string }): Promise<ChannelActionResult> {
  const parsed = postInput.safeParse(input)
  if (!parsed.success) return INVALID
  const { eventId, contentHash: content_hash } = parsed.data
  return settle(await api.sendChannelPost(eventId, { content_hash }), { postsToTelegram: true })
}

export async function updateChannelPost(input: { eventId: string; contentHash: string }): Promise<ChannelActionResult> {
  const parsed = postInput.safeParse(input)
  if (!parsed.success) return INVALID
  const { eventId, contentHash: content_hash } = parsed.data
  return settle(await api.updateChannelPost(eventId, { content_hash }), { postsToTelegram: true })
}

export async function deleteChannelPost(input: { eventId: string; publicationId: string }): Promise<ChannelActionResult> {
  const parsed = publicationInput.safeParse(input)
  if (!parsed.success) return INVALID
  const { eventId, publicationId } = parsed.data
  return settle(await api.deleteChannelPost(eventId, { publication_id: publicationId }))
}

/** The operator checked the channel: the uncertain send is not there, so allow a new send. */
export async function resolveChannelPost(input: { eventId: string; publicationId: string }): Promise<ChannelActionResult> {
  const parsed = publicationInput.safeParse(input)
  if (!parsed.success) return INVALID
  const { eventId, publicationId } = parsed.data
  return settle(await api.resolveChannelPost(eventId, publicationId, { outcome: "not_in_channel" }))
}
