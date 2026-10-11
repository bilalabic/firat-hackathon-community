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
import type { ActionResult } from "@/lib/form-state"

const uuid = z.uuid()
const contentHash = z.string().regex(/^[0-9a-f]{64}$/)

const postInput = z.object({ eventId: uuid, contentHash })
const publicationInput = z.object({ eventId: uuid, publicationId: uuid })

function settle(result: ApiResult<ChannelActionOut>): ActionResult {
  if (!result.ok) {
    // 409 (stale preview, already posted) and 502 (Telegram refused; the attempt is
    // recorded) both change what the page shows: re-render it. The message stays visible.
    if (result.error.kind === "conflict" || result.error.kind === "upstream") refresh()
    return { ok: false, message: result.error.message }
  }
  refresh()
  return { ok: true, message: result.data.message }
}

export async function sendChannelPost(input: { eventId: string; contentHash: string }): Promise<ActionResult> {
  const parsed = postInput.safeParse(input)
  if (!parsed.success) return { ok: false, message: "Invalid channel post request." }
  const { eventId, contentHash: content_hash } = parsed.data
  return settle(await api.sendChannelPost(eventId, { content_hash }))
}

export async function updateChannelPost(input: { eventId: string; contentHash: string }): Promise<ActionResult> {
  const parsed = postInput.safeParse(input)
  if (!parsed.success) return { ok: false, message: "Invalid channel post request." }
  const { eventId, contentHash: content_hash } = parsed.data
  return settle(await api.updateChannelPost(eventId, { content_hash }))
}

export async function deleteChannelPost(input: { eventId: string; publicationId: string }): Promise<ActionResult> {
  const parsed = publicationInput.safeParse(input)
  if (!parsed.success) return { ok: false, message: "Invalid channel post request." }
  const { eventId, publicationId } = parsed.data
  return settle(await api.deleteChannelPost(eventId, { publication_id: publicationId }))
}

/** The operator checked the channel: the uncertain send is not there, so allow a new send. */
export async function resolveChannelPost(input: { eventId: string; publicationId: string }): Promise<ActionResult> {
  const parsed = publicationInput.safeParse(input)
  if (!parsed.success) return { ok: false, message: "Invalid channel post request." }
  const { eventId, publicationId } = parsed.data
  return settle(await api.resolveChannelPost(eventId, publicationId, { outcome: "not_in_channel" }))
}
