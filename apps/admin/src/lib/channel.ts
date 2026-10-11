// Labels and pure helpers for Telegram channel publishing (V1.1a). Which actions are
// possible always comes from the API (`can_send`, `can_update`, `can_delete`,
// `can_resolve`); this file only describes how states and actions are presented.
// Type-only imports: safe to use from Client Components.

import type {
  ChannelHistory,
  ChannelPreview,
  Publication,
  PublicationStatus,
  PostState,
} from "@/lib/api/types"
import { safeHttpUrl } from "@/lib/urls"

export const CAPTION_LIMIT = 1024

type BadgeVariant = "default" | "secondary" | "outline" | "destructive"

const POST_STATE_META: Record<PostState, { label: string; variant: BadgeVariant }> = {
  not_posted: { label: "Not posted", variant: "outline" },
  sending: { label: "Sending", variant: "secondary" },
  uncertain: { label: "Uncertain", variant: "destructive" },
  posted: { label: "Posted", variant: "default" },
  changed: { label: "Changed since post", variant: "secondary" },
  not_public: { label: "Live, event not public", variant: "destructive" },
}

/** A state this admin does not know yet (a newer API) is shown as is. */
export function postStateMeta(state: string): { label: string; variant: BadgeVariant } {
  return POST_STATE_META[state as PostState] ?? { label: state, variant: "outline" }
}

export const PUBLICATION_STATUS_LABELS: Record<PublicationStatus, string> = {
  draft: "Sending",
  sent: "Sent",
  edited: "Edited",
  deleted: "Deleted",
  failed: "Failed",
}

/** An uncertain send is failed, but the message may be in the channel. */
export function publicationStatusLabel(post: Pick<Publication, "status" | "uncertain">): string {
  return post.uncertain ? "Failed, outcome unknown" : PUBLICATION_STATUS_LABELS[post.status]
}

export type ChannelAction = "send" | "update" | "delete" | "resolve"

export type ChannelActionMeta = {
  label: string
  /** Shown in the confirmation dialog; every channel action is confirmed (public or destructive). */
  confirm: string
  destructive?: boolean
}

export function channelActionMeta(action: ChannelAction, cardChanged = false): ChannelActionMeta {
  switch (action) {
    case "send":
      return {
        label: "Send to channel",
        confirm:
          "The post is published in the public Telegram channel right away, with the caption and card shown above.",
      }
    case "update":
      return {
        label: "Update post",
        confirm: cardChanged
          ? "The live channel post gets the caption shown above, and its card image is replaced."
          : "The live channel post gets the caption shown above. The card image stays the same.",
      }
    case "delete":
      return {
        label: "Delete post",
        confirm:
          "The post is deleted from the Telegram channel for everyone. Telegram may refuse posts older than 48 hours; the error then says what to do.",
        destructive: true,
      }
    case "resolve":
      return {
        label: "Mark as not posted",
        confirm:
          "Confirm only after checking the channel: the message is not there (or you deleted it there by hand). The attempt is recorded as failed and the event can be sent again. If the message is in the channel, a new send would post it twice.",
      }
  }
}

/** Audit `action` values written by the API, as shown in the history. */
const AUDIT_ACTION_LABELS: Record<string, string> = {
  telegram_post: "Send",
  telegram_update: "Update",
  telegram_delete: "Delete",
  telegram_resolve: "Resolve",
}

/** Audit `detail.outcome` values: ChannelActionOut outcomes plus the error outcomes. */
const OUTCOME_LABELS: Record<string, string> = {
  sent: "Sent",
  sent_as_text: "Sent as text (card fallback)",
  edited: "Edited",
  edited_caption_only: "Caption edited, card kept",
  unchanged: "Unchanged (already up to date)",
  deleted: "Deleted",
  already_gone: "Already gone from the channel",
  not_in_channel: "Marked as not in the channel",
  failed: "Failed",
  uncertain: "Outcome unknown (may be in the channel)",
  interrupted: "Interrupted send retired",
  conflict: "Refused: the post changed meanwhile",
}

export function actorLabel(actor: string): string {
  if (actor === "admin_ui") return "Admin UI"
  if (actor.startsWith("telegram:")) return `Admin bot (${actor.slice("telegram:".length)})`
  return actor
}

export type Notice = { tone: "info" | "warning"; title: string; text: string }

/** The one sentence that explains the current state and what can be done next. */
export function channelNotice(preview: ChannelPreview): Notice {
  if (!preview.configured) {
    const deletable = preview.can_delete
      ? " The existing post can still be deleted."
      : preview.can_resolve
        ? " The uncertain send can still be marked as not posted."
        : ""
    return {
      tone: "warning",
      title: "Channel publishing is not configured",
      text: `${preview.config_problem ?? "Telegram is not configured."} Restart the API after changing services/api/.env.${deletable}`,
    }
  }
  const state: string = preview.post_state
  switch (state) {
    case "not_posted":
      return preview.event_status === "published"
        ? { tone: "info", title: "Not posted yet", text: "Check the caption and card, then send the post." }
        : {
            tone: "info",
            title: "Event not published",
            text: "Only published events can be posted to the channel. Publish the event first.",
          }
    case "sending":
      return {
        tone: "warning",
        title: "A send is in progress",
        text: "Reload the page in a moment. If this does not clear, check the channel before sending again.",
      }
    case "posted":
      return { tone: "info", title: "Posted", text: "The channel post matches the current caption and card." }
    case "changed":
      return {
        tone: "warning",
        title: "The event changed since it was posted",
        text: preview.card_changed
          ? "The caption or card in the channel is outdated. Update replaces the caption and the card image."
          : "The caption in the channel is outdated. Update edits it; the card image stays the same.",
      }
    case "not_public":
      return {
        tone: "warning",
        title: "The event is no longer public",
        text: "Its channel post is still live. Delete it if it should not stay in the channel.",
      }
    case "uncertain":
      return {
        tone: "warning",
        title: "The last send may have reached the channel",
        text: "Sending timed out, got an unreadable answer or was interrupted, so the message may already be in the channel. Check the channel; if it is not there, mark it as not posted to allow a new send.",
      }
    default:
      return {
        tone: "warning",
        title: `Unknown post state: ${state}`,
        text: "The API reported a state this admin does not know. Check the channel before acting, and update the admin.",
      }
  }
}

export type HistoryRow = {
  at: string
  action: string
  actor: string
  outcome: string
  /** Telegram message_id of the post the action applied to, when known. */
  messageId: string | null
  /** Current status of that post. */
  postStatus: string | null
}

/** One row per audited operation (newest first, as the API returns them). */
export function historyRows(history: ChannelHistory): HistoryRow[] {
  const posts = new Map<string, Publication>(history.posts.map((post) => [post.id, post]))
  return history.actions.map((entry) => {
    const id = typeof entry.detail.publication_id === "string" ? entry.detail.publication_id : null
    const outcome = typeof entry.detail.outcome === "string" ? entry.detail.outcome : null
    const post = id ? posts.get(id) : undefined
    return {
      at: entry.at,
      action: AUDIT_ACTION_LABELS[entry.action] ?? entry.action,
      actor: actorLabel(entry.actor),
      outcome: outcome ? (OUTCOME_LABELS[outcome] ?? outcome) : "—",
      messageId: post?.external_id ?? null,
      postStatus: post ? publicationStatusLabel(post) : null,
    }
  })
}

// --- caption rendering -------------------------------------------------------------------

/**
 * The caption is Telegram "HTML style" (parse_mode HTML): text with `&lt;`, `&gt;`,
 * `&amp;`, `&quot;` (and numeric) entities and a few tags. It is parsed into nodes so
 * the preview renders it with React, never as raw HTML. Unknown or unbalanced tags are
 * kept as literal text, which makes a template mistake visible instead of hiding it.
 */
export type CaptionTag = "b" | "i" | "u" | "s" | "code" | "pre" | "a"
export type CaptionNode = string | { tag: CaptionTag; href?: string | null; children: CaptionNode[] }

const TAG_ALIASES: Record<string, CaptionTag> = {
  b: "b",
  strong: "b",
  i: "i",
  em: "i",
  u: "u",
  ins: "u",
  s: "s",
  strike: "s",
  del: "s",
  code: "code",
  pre: "pre",
  a: "a",
}

const NAMED_ENTITIES: Record<string, string> = { lt: "<", gt: ">", amp: "&", quot: '"' }

export function decodeEntities(text: string): string {
  return text.replace(/&(#x[0-9a-f]+|#[0-9]+|[a-z]+);/gi, (match, name: string) => {
    if (name[0] === "#") {
      const code = name[1] === "x" || name[1] === "X" ? parseInt(name.slice(2), 16) : parseInt(name.slice(1), 10)
      return code > 0 && code <= 0x10ffff ? String.fromCodePoint(code) : match
    }
    return NAMED_ENTITIES[name.toLowerCase()] ?? match
  })
}

function hrefOf(attributes: string): string | null {
  const match = /\bhref\s*=\s*"([^"]*)"/i.exec(attributes)
  return match ? safeHttpUrl(decodeEntities(match[1])) : null
}

export function parseCaptionHtml(html: string): CaptionNode[] {
  type Frame = { tag: CaptionTag | null; name: string; href?: string | null; children: CaptionNode[] }
  const root: Frame = { tag: null, name: "", children: [] }
  const stack: Frame[] = [root]
  const push = (node: CaptionNode) => {
    const children = stack[stack.length - 1].children
    const last = children[children.length - 1]
    if (typeof node === "string" && typeof last === "string") children[children.length - 1] = last + node
    else children.push(node)
  }

  const token = /<(\/?)([a-z][a-z0-9-]*)((?:\s[^<>]*)?)>/gi
  let index = 0
  for (let match = token.exec(html); match; match = token.exec(html)) {
    if (match.index > index) push(decodeEntities(html.slice(index, match.index)))
    index = token.lastIndex
    const [raw, closing, rawName, attributes] = match
    const name = rawName.toLowerCase()
    const tag = TAG_ALIASES[name]
    if (!tag) {
      push(raw)
    } else if (!closing) {
      stack.push({ tag, name, href: tag === "a" ? hrefOf(attributes) : undefined, children: [] })
    } else if (stack.length > 1 && stack[stack.length - 1].name === name) {
      const frame = stack.pop()!
      push({ tag, ...(tag === "a" ? { href: frame.href } : {}), children: frame.children })
    } else {
      push(raw)
    }
  }
  if (index < html.length) push(decodeEntities(html.slice(index)))

  // Unclosed tags: their opening tag is shown as text, their content is kept.
  while (stack.length > 1) {
    const frame = stack.pop()!
    const parent = stack[stack.length - 1].children
    parent.push(`<${frame.name}>`, ...frame.children)
  }
  return root.children
}
