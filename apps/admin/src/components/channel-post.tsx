// Telegram channel section of the event page (V1.1a): the caption and card exactly as
// the API would send them, the current post, Send / Update / Delete, and the history.
// Reads make no Telegram call, so the section streams in quickly.

import { InfoIcon, TriangleAlertIcon } from "lucide-react"

import { ApiErrorState } from "@/components/api-error-state"
import { ChannelPostActions } from "@/components/channel-post-actions"
import { ExternalLink } from "@/components/external-link"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { api } from "@/lib/api/client"
import type { ChannelHistory, ChannelPreview, Publication } from "@/lib/api/types"
import {
  CAPTION_LIMIT,
  channelNotice,
  historyRows,
  parseCaptionHtml,
  postStateMeta,
  publicationStatusLabel,
  type CaptionNode,
} from "@/lib/channel"
import { formatDateTime } from "@/lib/format"
import { safeHttpUrl } from "@/lib/urls"

const TITLE = "Telegram channel"
const DESCRIPTION = "The channel post for this event: caption and card as they are sent, then the post history."

function Facts({ items }: { items: [string, React.ReactNode][] }) {
  return (
    <dl className="grid gap-x-4 gap-y-1 text-sm sm:grid-cols-[9rem_1fr]">
      {items.map(([label, value]) => (
        <div key={label} className="contents">
          <dt className="text-muted-foreground">{label}</dt>
          <dd className="break-words">{value}</dd>
        </div>
      ))}
    </dl>
  )
}

function CaptionNodes({ nodes }: { nodes: CaptionNode[] }) {
  return nodes.map((node, index) => {
    if (typeof node === "string") return node
    const children = <CaptionNodes nodes={node.children} />
    switch (node.tag) {
      case "b":
        return <strong key={index}>{children}</strong>
      case "i":
        return <em key={index}>{children}</em>
      case "u":
        return <u key={index}>{children}</u>
      case "s":
        return <s key={index}>{children}</s>
      case "code":
      case "pre":
        return (
          <code key={index} className="font-mono text-xs">
            {children}
          </code>
        )
      case "a":
        return node.href ? (
          <a
            key={index}
            href={node.href}
            title={node.href}
            target="_blank"
            rel="noopener noreferrer"
            className="text-primary underline underline-offset-4"
          >
            {children}
          </a>
        ) : (
          <span key={index}>{children}</span>
        )
    }
  })
}

/** Card image above the caption, roughly as a Telegram photo post shows it. */
function PostPreview({ preview }: { preview: ChannelPreview }) {
  const image = safeHttpUrl(preview.image_url)
  return (
    <figure className="grid max-w-md gap-0 overflow-hidden rounded-xl border bg-muted/40">
      {image ? (
        // The card is served by the public site (WEB_BASE_URL); a plain <img> avoids
        // configuring next/image remote patterns for one preview.
        // eslint-disable-next-line @next/next/no-img-element
        <img src={image} alt={`Event card for ${preview.title}`} className="aspect-[1200/630] w-full bg-muted object-cover" />
      ) : (
        <div className="flex aspect-[1200/630] items-center justify-center bg-muted p-4 text-center text-sm text-muted-foreground">
          No card image: WEB_BASE_URL is not set.
        </div>
      )}
      <figcaption className="p-3 text-sm leading-relaxed whitespace-pre-wrap break-words">
        <CaptionNodes nodes={parseCaptionHtml(preview.caption_html)} />
      </figcaption>
    </figure>
  )
}

function CurrentPost({ post, preview }: { post: Publication; preview: ChannelPreview }) {
  const items: [string, React.ReactNode][] = [
    ["Message id", post.external_id ?? "—"],
    ["Status", publicationStatusLabel(post)],
    ["Type", post.message_type === "text" ? "Text with link preview (card fallback)" : post.message_type === "photo" ? "Photo with caption" : "—"],
    ["Version", String(post.content_version)],
    ["Sent", formatDateTime(post.sent_at)],
    ["Last edited", formatDateTime(post.edited_at)],
  ]
  if (preview.card_changed && post.image_url) {
    items.push(["Card in the post", <ExternalLink key="card" href={post.image_url} />])
  }
  if (post.error) items.push(["Note", post.error])
  return (
    <div className="grid gap-2 rounded-lg border p-3">
      <div className="text-sm font-medium">Current post</div>
      <Facts items={items} />
    </div>
  )
}

function History({ history }: { history: ChannelHistory }) {
  const rows = historyRows(history)
  return (
    <div className="grid gap-2">
      <h3 className="text-sm font-medium">Publication history</h3>
      <div className="overflow-hidden rounded-lg border">
        <Table>
          <TableHeader className="bg-muted">
            <TableRow>
              <TableHead>Time</TableHead>
              <TableHead>Action</TableHead>
              <TableHead>By</TableHead>
              <TableHead>Outcome</TableHead>
              <TableHead>Message id</TableHead>
              <TableHead>Post status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={6} className="h-16 text-center text-muted-foreground">
                  Nothing was sent to the channel for this event yet.
                </TableCell>
              </TableRow>
            ) : (
              rows.map((row, index) => (
                <TableRow key={`${row.at}-${index}`}>
                  <TableCell>{formatDateTime(row.at)}</TableCell>
                  <TableCell>{row.action}</TableCell>
                  <TableCell>{row.actor}</TableCell>
                  <TableCell className="whitespace-normal">{row.outcome}</TableCell>
                  <TableCell className="font-mono text-xs">{row.messageId ?? "—"}</TableCell>
                  <TableCell>{row.postStatus ?? "—"}</TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>
      {history.posts.some((post) => post.status === "failed" && post.error) && (
        <ul className="grid gap-1 text-sm text-muted-foreground">
          {history.posts
            .filter((post) => post.status === "failed" && post.error)
            .map((post) => (
              <li key={post.id}>
                {post.uncertain ? "Uncertain attempt" : "Failed attempt"} ({formatDateTime(post.created_at)}): {post.error}
              </li>
            ))}
        </ul>
      )}
    </div>
  )
}

function SectionCard({ preview, children }: { preview?: ChannelPreview; children: React.ReactNode }) {
  const state = preview ? postStateMeta(preview.post_state) : null
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-2">
          {TITLE}
          {state && <Badge variant={state.variant}>{state.label}</Badge>}
        </CardTitle>
        <CardDescription>{DESCRIPTION}</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4">{children}</CardContent>
    </Card>
  )
}

export function ChannelPostFallback() {
  return (
    <SectionCard>
      <p role="status" className="text-sm text-muted-foreground">
        Loading the channel preview…
      </p>
      <Skeleton className="h-48 w-full max-w-md" />
    </SectionCard>
  )
}

export async function ChannelPostSection({ eventId }: { eventId: string }) {
  const [previewResult, historyResult] = await Promise.all([
    api.previewChannelPost(eventId),
    api.channelPostHistory(eventId),
  ])
  if (!previewResult.ok) {
    return (
      <SectionCard>
        <ApiErrorState error={previewResult.error} />
      </SectionCard>
    )
  }

  const preview = previewResult.data
  const notice = channelNotice(preview)
  const post = preview.current_post
  return (
    <SectionCard preview={preview}>
      <Alert variant={notice.tone === "warning" ? "warning" : "default"}>
        {notice.tone === "warning" ? <TriangleAlertIcon /> : <InfoIcon />}
        <AlertTitle>{notice.title}</AlertTitle>
        <AlertDescription>{notice.text}</AlertDescription>
      </Alert>
      <div className="grid items-start gap-4 @3xl/main:grid-cols-[minmax(0,28rem)_1fr]">
        <PostPreview preview={preview} />
        <div className="grid gap-4">
          <Facts
            items={[
              [
                "Caption length",
                `${preview.caption_length} / ${CAPTION_LIMIT}${preview.caption_truncated ? " (summary shortened to fit)" : ""}`,
              ],
              ["Card image", preview.image_url ? <ExternalLink key="card" href={preview.image_url} /> : "—"],
              ["Detail page", preview.detail_url ? <ExternalLink key="detail" href={preview.detail_url} /> : "—"],
            ]}
          />
          {post && <CurrentPost post={post} preview={preview} />}
          <ChannelPostActions
            eventId={preview.event_id}
            eventTitle={preview.title}
            contentHash={preview.content_hash}
            publicationId={post?.id ?? null}
            cardChanged={preview.card_changed}
            allowed={{
              send: preview.can_send,
              update: preview.can_update,
              delete: preview.can_delete,
              resolve: preview.can_resolve,
            }}
          />
        </div>
      </div>
      {historyResult.ok ? <History history={historyResult.data} /> : <ApiErrorState error={historyResult.error} />}
    </SectionCard>
  )
}
