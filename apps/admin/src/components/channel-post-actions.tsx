"use client"

// Send / Update / Delete / Mark as not posted for an event's channel post. Only the
// actions the API offers (`can_send`, `can_update`, `can_delete`, `can_resolve`) are
// shown; each one is confirmed first, because it is public (send, update), destructive
// (delete) or allows a second post (resolve).

import { useEffect, useRef, useState, useTransition } from "react"
import { CircleAlertIcon, TriangleAlertIcon } from "lucide-react"
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
import {
  deleteChannelPost,
  resolveChannelPost,
  sendChannelPost,
  updateChannelPost,
} from "@/lib/actions/channel"
import {
  channelActionMeta,
  isUnknownOutcome,
  type ChannelAction,
  type ChannelActionResult,
} from "@/lib/channel"

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
  /** The draft, uncertain or live post (Delete and resolve apply to it). */
  publicationId: string | null
  cardChanged: boolean
  allowed: Record<ChannelAction, boolean>
}) {
  const groupRef = useRef<HTMLDivElement>(null)
  const openerRef = useRef<HTMLElement | null>(null)
  const [pending, startTransition] = useTransition()
  const [error, setError] = useState<{ message: string; unknownOutcome: boolean } | null>(null)
  const [running, setRunning] = useState<ChannelAction | null>(null)
  // Set synchronously, so a second confirm before React re-renders is ignored.
  const inFlight = useRef(false)
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

  const run = (action: ChannelAction) => {
    if (inFlight.current) return
    inFlight.current = true
    setError(null)
    setRunning(action)
    startTransition(async () => {
      try {
        let result: ChannelActionResult
        if (action === "delete" || action === "resolve") {
          const act = action === "delete" ? deleteChannelPost : resolveChannelPost
          result = publicationId
            ? await act({ eventId, publicationId })
            : { ok: false, kind: "invalid", message: "There is no post for this action." }
        } else {
          const send = action === "send" ? sendChannelPost : updateChannelPost
          result = await send({ eventId, contentHash })
        }
        // Errors are announced by the alert below (role=alert), successes by a toast.
        if (result.ok) toast.success(result.message)
        else setError({ message: result.message, unknownOutcome: isUnknownOutcome(result.kind) })
      } finally {
        inFlight.current = false
      }
    })
  }

  const actions: ChannelAction[] = ["resolve", "send", "update", "delete"]
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
              variant={destructive ? "destructive" : action === "resolve" ? "outline" : "default"}
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
            {running === "resolve" ? "Saving…" : "Waiting for Telegram…"}
          </span>
        )}
      </div>
      {error &&
        (error.unknownOutcome ? (
          <Alert variant="warning">
            <TriangleAlertIcon />
            <AlertTitle>Outcome unknown</AlertTitle>
            <AlertDescription>{error.message}</AlertDescription>
          </Alert>
        ) : (
          <Alert variant="destructive">
            <CircleAlertIcon />
            <AlertTitle>Channel action failed</AlertTitle>
            <AlertDescription>{error.message}</AlertDescription>
          </Alert>
        ))}
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
                disabled={pending}
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
