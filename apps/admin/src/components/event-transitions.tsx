"use client"

// State-machine actions for one event. Only the actions the API lists in
// `allowed_actions` are offered; guards are still checked by the API (409).

import { useEffect, useId, useRef, useState, useTransition, type RefObject } from "react"
import Link from "next/link"
import { CircleAlertIcon, EllipsisVerticalIcon } from "lucide-react"
import { toast } from "sonner"

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
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { transitionEvent } from "@/lib/actions/events"
import type { EventAction } from "@/lib/api/types"
import { ACTION_META, needsDialog } from "@/lib/events"

/** The first enabled button inside `element`, else the element itself (if still on the page). */
function focusableIn(element: HTMLElement | null): HTMLElement | null {
  if (!element?.isConnected) return null
  if (element.matches("button:not(:disabled)")) return element
  return element.querySelector<HTMLElement>("button:not(:disabled)") ?? element
}

/**
 * Sends a transition. When it settles and focus was lost (the clicked button was
 * disabled while pending, or removed because the status changed), focus moves to
 * `focusTarget` (its first enabled button, or the element itself).
 */
function useEventTransition(eventId: string, focusTarget: RefObject<HTMLElement | null>) {
  const [pending, startTransition] = useTransition()
  const [error, setError] = useState<string | null>(null)
  const wasPending = useRef(false)

  useEffect(() => {
    if (wasPending.current && !pending) {
      const active = document.activeElement
      if (!active || active === document.body || !active.isConnected) {
        focusableIn(focusTarget.current)?.focus()
      }
    }
    wasPending.current = pending
  }, [pending, focusTarget])

  const run = (action: EventAction, reason?: string) =>
    startTransition(async () => {
      const result = await transitionEvent({ eventId, action, reason })
      if (result.ok) {
        setError(null)
        toast.success(result.message)
      } else {
        setError(result.message)
        toast.error(result.message)
      }
    })
  return { pending, error, run }
}

function TransitionDialog({
  action,
  eventTitle,
  returnFocus,
  fallbackFocus,
  onClose,
  onConfirm,
}: {
  action: EventAction | null
  eventTitle: string
  /** Where focus goes when the dialog closes (Esc, Cancel or confirm). */
  returnFocus: RefObject<HTMLElement | null>
  /** Used when `returnFocus` is gone or disabled (e.g. while the action is pending). */
  fallbackFocus: RefObject<HTMLElement | null>
  onClose: () => void
  onConfirm: (action: EventAction, reason?: string) => void
}) {
  const reasonId = useId()
  const [reason, setReason] = useState("")
  // Keep the last action rendered while the dialog animates out, so the popup stays
  // mounted and Base UI can restore focus.
  const [shown, setShown] = useState<EventAction | null>(action)
  if (action !== null && action !== shown) setShown(action)
  const meta = shown ? ACTION_META[shown] : null

  return (
    <AlertDialog
      open={action !== null}
      onOpenChange={(open) => {
        if (!open) {
          setReason("")
          onClose()
        }
      }}
    >
      {shown && meta && (
        <AlertDialogContent className="data-[size=default]:sm:max-w-md" finalFocus={() => {
            const opener = returnFocus.current
            if (opener?.isConnected && !opener.matches(":disabled")) return opener
            return focusableIn(fallbackFocus.current) ?? true
          }}
        >
          <form
            className="grid gap-4"
            onSubmit={(event) => {
              event.preventDefault()
              onConfirm(shown, reason.trim() || undefined)
              setReason("")
              onClose()
            }}
          >
            <AlertDialogHeader>
              <AlertDialogTitle>
                {meta.label}: {eventTitle}
              </AlertDialogTitle>
              {meta.confirm && <AlertDialogDescription>{meta.confirm}</AlertDialogDescription>}
            </AlertDialogHeader>
            {meta.reason && (
              <div className="grid gap-2">
                <Label htmlFor={reasonId}>
                  Reason {meta.reason === "required" ? "(required)" : "(optional)"}
                </Label>
                <Textarea
                  id={reasonId}
                  value={reason}
                  onChange={(event) => setReason(event.target.value)}
                  required={meta.reason === "required"}
                  maxLength={1000}
                  rows={3}
                  autoFocus
                />
              </div>
            )}
            <AlertDialogFooter>
              <AlertDialogCancel>Cancel</AlertDialogCancel>
              <Button
                type="submit"
                variant={meta.destructive ? "destructive" : "default"}
                disabled={meta.reason === "required" && reason.trim() === ""}
              >
                {meta.label}
              </Button>
            </AlertDialogFooter>
          </form>
        </AlertDialogContent>
      )}
    </AlertDialog>
  )
}

/** Buttons for every allowed action, with an inline error for 409/422 results. */
export function EventActionsBar({
  eventId,
  eventTitle,
  actions,
}: {
  eventId: string
  eventTitle: string
  actions: EventAction[]
}) {
  const groupRef = useRef<HTMLDivElement>(null)
  const openerRef = useRef<HTMLElement | null>(null)
  const { pending, error, run } = useEventTransition(eventId, groupRef)
  const [dialog, setDialog] = useState<EventAction | null>(null)

  return (
    <div className="grid gap-3">
      <div
        ref={groupRef}
        role="group"
        aria-label="Status actions"
        tabIndex={-1}
        className="flex flex-wrap items-center gap-2 outline-none"
        aria-busy={pending}
      >
        {actions.length === 0 && (
          <span className="text-sm text-muted-foreground">No status changes are possible from here.</span>
        )}
        {actions.map((action) => (
          <Button
            key={action}
            size="sm"
            variant={ACTION_META[action].destructive ? "destructive" : "outline"}
            disabled={pending}
            onClick={(event) => {
              openerRef.current = event.currentTarget
              if (needsDialog(action)) setDialog(action)
              else run(action)
            }}
          >
            {ACTION_META[action].label}
          </Button>
        ))}
      </div>
      {error && (
        <Alert variant="destructive">
          <CircleAlertIcon />
          <AlertTitle>Action not applied</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      <TransitionDialog
        action={dialog}
        eventTitle={eventTitle}
        returnFocus={openerRef}
        fallbackFocus={groupRef}
        onClose={() => setDialog(null)}
        onConfirm={run}
      />
    </div>
  )
}

/** Row menu for the events table: edit, review, then the allowed actions. */
export function EventRowActions({
  eventId,
  eventTitle,
  actions,
}: {
  eventId: string
  eventTitle: string
  actions: EventAction[]
}) {
  const triggerRef = useRef<HTMLButtonElement>(null)
  const { pending, run } = useEventTransition(eventId, triggerRef)
  const [dialog, setDialog] = useState<EventAction | null>(null)

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger
          render={
            <Button
              ref={triggerRef}
              variant="ghost"
              className="flex size-8 text-muted-foreground data-open:bg-muted"
              size="icon"
              disabled={pending}
            />
          }
        >
          <EllipsisVerticalIcon />
          <span className="sr-only">Actions for {eventTitle}</span>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-44">
          <DropdownMenuItem render={<Link href={`/events/${eventId}`} />}>Edit</DropdownMenuItem>
          <DropdownMenuItem render={<Link href={`/events/${eventId}/review`} />}>Review</DropdownMenuItem>
          {actions.length > 0 && <DropdownMenuSeparator />}
          {actions.map((action) => (
            <DropdownMenuItem
              key={action}
              variant={ACTION_META[action].destructive ? "destructive" : "default"}
              onClick={() => (needsDialog(action) ? setDialog(action) : run(action))}
            >
              {ACTION_META[action].label}
            </DropdownMenuItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>
      <TransitionDialog
        action={dialog}
        eventTitle={eventTitle}
        returnFocus={triggerRef}
        fallbackFocus={triggerRef}
        onClose={() => setDialog(null)}
        onConfirm={run}
      />
    </>
  )
}
