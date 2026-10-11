import { describe, expect, it } from "vitest"

import type { ChannelHistory, ChannelPreview, Publication } from "@/lib/api/types"

import {
  actorLabel,
  channelActionMeta,
  channelNotice,
  decodeEntities,
  historyRows,
  isUnknownOutcome,
  parseCaptionHtml,
  postStateMeta,
  publicationStatusLabel,
} from "./channel"

const POST: Publication = {
  id: "11111111-1111-4111-8111-111111111111",
  event_id: "22222222-2222-4222-8222-222222222222",
  platform: "telegram",
  target: "-1001234567890",
  external_id: "42",
  content_hash: "a".repeat(64),
  content_version: 2,
  body: "<b>X</b>",
  image_url: "https://example.org/hackathonlar/x/opengraph-image?v=1",
  message_type: "photo",
  status: "edited",
  uncertain: false,
  sent_at: "2026-10-07T10:00:00Z",
  edited_at: "2026-10-07T11:00:00Z",
  deleted_at: null,
  error: null,
  created_at: "2026-10-07T09:59:00Z",
}

function preview(overrides: Partial<ChannelPreview> = {}): ChannelPreview {
  return {
    event_id: POST.event_id,
    slug: "x",
    title: "X",
    event_status: "published",
    configured: true,
    config_problem: null,
    caption_html: "<b>X</b>",
    caption_text: "X",
    caption_length: 1,
    caption_truncated: false,
    image_url: "https://example.org/hackathonlar/x/opengraph-image?v=2",
    detail_url: "https://example.org/hackathonlar/x",
    content_hash: "b".repeat(64),
    post_state: "not_posted",
    card_changed: false,
    current_post: null,
    can_send: true,
    can_update: false,
    can_delete: false,
    can_resolve: false,
    ...overrides,
  }
}

describe("parseCaptionHtml", () => {
  it("parses the caption tags and decodes entities in text and href", () => {
    const nodes = parseCaptionHtml(
      '<b>Borsa &amp; İTÜ</b>\n🔗 <a href="https://example.org/a?x=1&amp;y=2">Resmî sayfa</a>'
    )
    expect(nodes).toEqual([
      { tag: "b", children: ["Borsa & İTÜ"] },
      "\n🔗 ",
      { tag: "a", href: "https://example.org/a?x=1&y=2", children: ["Resmî sayfa"] },
    ])
  })

  it("never links a non-http(s) href", () => {
    expect(parseCaptionHtml('<a href="javascript:alert(1)">x</a>')).toEqual([{ tag: "a", href: null, children: ["x"] }])
  })

  it("renders single-quoted and unquoted hrefs as unlinked text", () => {
    // Only the double-quoted form our templates produce becomes a link (a span otherwise).
    expect(parseCaptionHtml("<a href='https://example.org'>x</a>")).toEqual([{ tag: "a", href: null, children: ["x"] }])
    expect(parseCaptionHtml("<a href=https://example.org>x</a>")).toEqual([{ tag: "a", href: null, children: ["x"] }])
  })

  it("decodes numeric entities inside href", () => {
    expect(parseCaptionHtml('<a href="https://example.org/?a=1&#38;b=&#x32;">x</a>')).toEqual([
      { tag: "a", href: "https://example.org/?a=1&b=2", children: ["x"] },
    ])
  })

  it("keeps unknown, stray and unclosed tags as literal text", () => {
    expect(parseCaptionHtml("<script>x</script>")).toEqual(["<script>x</script>"])
    expect(parseCaptionHtml("a</b>c")).toEqual(["a</b>c"])
    expect(parseCaptionHtml("<b>open")).toEqual(["<b>", "open"])
  })

  it("maps Telegram tag aliases and nests", () => {
    expect(parseCaptionHtml("<strong>a<em>b</em></strong>")).toEqual([
      { tag: "b", children: ["a", { tag: "i", children: ["b"] }] },
    ])
  })
})

describe("decodeEntities", () => {
  it("decodes the Bot API entities and numeric references only", () => {
    expect(decodeEntities("&lt;&gt;&amp;&quot;&#39;&#x1F517;&nbsp;")).toBe("<>&\"'🔗&nbsp;")
  })
})

describe("channelNotice", () => {
  it("explains a missing channel configuration first", () => {
    const notice = channelNotice(
      preview({ configured: false, config_problem: "Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHANNEL_ID in services/api/.env." })
    )
    expect(notice).toMatchObject({ tone: "warning", title: "Channel publishing is not configured" })
    expect(notice.text).toContain("TELEGRAM_CHANNEL_ID")
  })

  it("distinguishes unpublished events, changes and live posts of hidden events", () => {
    expect(channelNotice(preview({ event_status: "approved" })).title).toBe("Event not published")
    expect(channelNotice(preview({ post_state: "changed", card_changed: true })).text).toMatch(/card image/)
    expect(channelNotice(preview({ post_state: "not_public" })).text).toMatch(/Delete/)
    expect(channelNotice(preview({ post_state: "posted" })).tone).toBe("info")
  })

  it("handles the uncertain state and unknown states defensively", () => {
    const uncertain = preview({ post_state: "uncertain", can_resolve: true })
    expect(channelNotice(uncertain).text).toMatch(/may already be in the channel/)
    const unknown = preview({ post_state: "later" as ChannelPreview["post_state"] })
    expect(channelNotice(unknown).title).toBe("Unknown post state: later")
    expect(postStateMeta("later")).toEqual({ label: "later", variant: "outline" })
    expect(postStateMeta("posted").label).toBe("Posted")
  })
})

describe("channel actions", () => {
  it("says whether an update replaces the card", () => {
    expect(channelActionMeta("update", true).confirm).toMatch(/card image is replaced/)
    expect(channelActionMeta("update", false).confirm).toMatch(/stays the same/)
    expect(channelActionMeta("delete").destructive).toBe(true)
    expect(channelActionMeta("resolve").label).toBe("Mark as not posted")
    expect(channelActionMeta("resolve").confirm).toMatch(/after checking the channel/)
  })

  it("treats 502, timeouts and dropped connections as an unknown outcome", () => {
    expect(["upstream", "timeout", "unreachable"].every((kind) => isUnknownOutcome(kind as "upstream"))).toBe(true)
    expect(["conflict", "not_found", "validation", "invalid"].some((kind) => isUnknownOutcome(kind as "conflict"))).toBe(false)
  })

  it("labels an uncertain failed send apart from a plain failure", () => {
    expect(publicationStatusLabel({ status: "failed", uncertain: true })).toBe("Failed, outcome unknown")
    expect(publicationStatusLabel({ status: "failed", uncertain: false })).toBe("Failed")
  })

  it("mentions resolving when the channel is not configured", () => {
    const notice = channelNotice(preview({ configured: false, config_problem: "x.", post_state: "uncertain", can_resolve: true }))
    expect(notice.text).toMatch(/marked as not posted/)
  })
})

describe("historyRows", () => {
  it("joins audit entries to their post for the message id and status", () => {
    const history: ChannelHistory = {
      posts: [POST],
      actions: [
        {
          actor: "telegram:123",
          action: "telegram_update",
          detail: { publication_id: POST.id, content_version: 2, outcome: "edited_caption_only" },
          at: "2026-10-07T11:00:00Z",
        },
        { actor: "admin_ui", action: "telegram_post", detail: { outcome: "failed" }, at: "2026-10-07T09:00:00Z" },
      ],
    }
    expect(historyRows(history)).toEqual([
      {
        at: "2026-10-07T11:00:00Z",
        action: "Update",
        actor: "Admin bot (123)",
        outcome: "Caption edited, card kept",
        messageId: "42",
        postStatus: "Edited",
      },
      { at: "2026-10-07T09:00:00Z", action: "Send", actor: "Admin UI", outcome: "Failed", messageId: null, postStatus: null },
    ])
  })

  it("labels resolve and the error outcomes", () => {
    const history: ChannelHistory = {
      posts: [{ ...POST, status: "failed", uncertain: false, external_id: null }],
      actions: [
        { actor: "admin_ui", action: "telegram_resolve", detail: { publication_id: POST.id, outcome: "not_in_channel" }, at: "2026-10-07T12:00:00Z" },
        { actor: "admin_ui", action: "telegram_post", detail: { publication_id: POST.id, outcome: "uncertain" }, at: "2026-10-07T11:00:00Z" },
        { actor: "admin_ui", action: "telegram_update", detail: { outcome: "conflict" }, at: "2026-10-07T10:00:00Z" },
        { actor: "admin_ui", action: "telegram_post", detail: { outcome: "interrupted" }, at: "2026-10-07T09:00:00Z" },
      ],
    }
    expect(historyRows(history).map((row) => [row.action, row.outcome, row.postStatus])).toEqual([
      ["Resolve", "Marked as not in the channel", "Failed"],
      ["Send", "Outcome unknown (may be in the channel)", "Failed"],
      ["Update", "Refused: the post changed meanwhile", null],
      ["Send", "Interrupted send retired", null],
    ])
  })

  it("shows unknown actors as is", () => {
    expect(actorLabel("someone")).toBe("someone")
  })
})
