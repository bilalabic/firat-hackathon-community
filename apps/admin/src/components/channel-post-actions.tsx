"use client"

// Send / Update / Delete for an event's channel post. Only the actions the API offers
// (`can_send`, `can_update`, `can_delete`) are enabled; each one is confirmed first,
// because it is public (send, update) or destructive (delete).

import { useEffect, useRef, useState, useTransition } from "react"
import { CircleAlertIcon } from "lucide-react"
import { toast } from "sonner"

import { focusableIn } from "@/components/event-transitions"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog"
import { Button } from "@/components/ui/button"
import { deleteChannelPost, sendChannelPost, updateChannelPost } from "@/lib/actions/channel"
import { channelActionMeta, type ChannelAction } from "@/lib/channel"
import type { ActionResult } from "@/lib/form-state"

export function ChannelPostActions({
  eventId,
  eventTitle,
  contentHash,
  publicationId,
  cardChanged,
  allowed,
}: {
  eventId: string
  eventTitle: string
  /** `content_hash` of the preview on screen; the API refuses the post if it changed. */
  contentHash: string
  /** The draft or live post (Delete applies to it). */
  publicationId: string | null
  cardChanged: boolean
  allowed: Record<ChannelAction, boolean>
}) {
  const groupRef = useRef<HTMLDivElement>(null)
  const openerRef = useRef<HTMLElement | null>(null)
  const [pending, startTransition] = useTransition()
  const [error, setError] = useState<string | null>(null)
  const [dialog, setDialog] = useState<ChannelAction | null>(null)
  // Keep the last action rendered while the dialog animates out (see TransitionDialog).
  const [shown, setShown] = useState<ChannelAction | null>(dialog)
  if (dialog !== null && dialog !== shown) setShown(dialog)
  const wasPending = useRef(false)

  // When the action settles and focus was lost (the button was disabled or removed),
  // move it back into the group.
  useEffect(() => {
    if (wasPending.current && !pending) {
      const active = document.activeElement
      if (!active || active === document.body || !active.isConnected) focusableIn(groupRef.current)?.focus()
    }
    wasPending.current = pending
  }, [pending])

  const run = (action: ChannelAction) =>
    startTransition(async () => {
      let result: ActionResult
      if (action === "delete") {
        result = publicationId
          ? await deleteChannelPost({ eventId, publicationId })
          : { ok: false, message: "There is no post to delete." }
      } else {
        const send = action === "send" ? sendChannelPost : updateChannelPost
        result = await send({ eventId, contentHash })
      }
      if (result.ok) {
        setError(null)
        toast.success(result.message)
      } else {
        setError(result.message)
        toast.error(result.message)
      }
    })

  const actions: ChannelAction[] = ["send", "update", "delete"]
  const offered = actions.filter((action) => allowed[action])
  const meta = shown ? channelActionMeta(shown, cardChanged) : null

  return (
    <div className="grid gap-3">
      <div
        ref={groupRef}
        role="group"
        aria-label="Channel post actions"
        tabIndex={-1}
        className="flex flex-wrap items-center gap-2 outline-none"
        aria-busy={pending}
      >
        {offered.length === 0 && (
          <span className="text-sm text-muted-foreground">No channel action is possible right now.</span>
        )}
        {offered.map((action) => {
          const { label, destructive } = channelActionMeta(action, cardChanged)
          return (
            <Button
              key={action}
              size="sm"
              variant={destructive ? "destructive" : "default"}
              disabled={pending}
              onClick={(event) => {
                openerRef.current = event.currentTarget
                setDialog(action)
              }}
            >
              {label}
            </Button>
          )
        })}
        {pending && (
          <span role="status" className="text-sm text-muted-foreground">
            Waiting for Telegram…
          </span>
        )}
      </div>
      {error && (
        <Alert variant="destructive">
          <CircleAlertIcon />
          <AlertTitle>Channel action not applied</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      <AlertDialog open={dialog !== null} onOpenChange={(open) => !open && setDialog(null)}>
        {shown && meta && (
          <AlertDialogContent
            className="data-[size=default]:sm:max-w-md"
            finalFocus={() => {
              const opener = openerRef.current
              if (opener?.isConnected && !opener.matches(":disabled")) return opener
              return focusableIn(groupRef.current) ?? true
            }}
          >
            <AlertDialogHeader>
              <AlertDialogTitle>
                {meta.label}: {eventTitle}
              </AlertDialogTitle>
              <AlertDialogDescription>{meta.confirm}</AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Cancel</AlertDialogCancel>
              <Button
                variant={meta.destructive ? "destructive" : "default"}
                onClick={() => {
                  run(shown)
                  setDialog(null)
                }}
              >
                {meta.label}
              </Button>
            </AlertDialogFooter>
          </AlertDialogContent>
        )}
      </AlertDialog>
    </div>
  )
}
