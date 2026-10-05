"use client"

// State-machine actions for one event. Only the actions the API lists in
// `allowed_actions` are offered; guards are still checked by the API (409).

import { useId, useState, useTransition } from "react"
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

function useEventTransition(eventId: string) {
  const [pending, startTransition] = useTransition()
  const [error, setError] = useState<string | null>(null)
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
  onOpenChange,
  onConfirm,
}: {
  action: EventAction | null
  eventTitle: string
  onOpenChange: (open: boolean) => void
  onConfirm: (action: EventAction, reason?: string) => void
}) {
  const reasonId = useId()
  const [reason, setReason] = useState("")
  const meta = action ? ACTION_META[action] : null

  return (
    <AlertDialog
      open={action !== null}
      onOpenChange={(open) => {
        if (!open) setReason("")
        onOpenChange(open)
      }}
    >
      {action && meta && (
        <AlertDialogContent className="data-[size=default]:sm:max-w-md">
          <form
            className="grid gap-4"
            onSubmit={(event) => {
              event.preventDefault()
              onConfirm(action, reason.trim() || undefined)
              setReason("")
              onOpenChange(false)
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
  const { pending, error, run } = useEventTransition(eventId)
  const [dialog, setDialog] = useState<EventAction | null>(null)

  return (
    <div className="grid gap-3">
      <div className="flex flex-wrap items-center gap-2" aria-busy={pending}>
        {actions.length === 0 && (
          <span className="text-sm text-muted-foreground">No status changes are possible from here.</span>
        )}
        {actions.map((action) => (
          <Button
            key={action}
            size="sm"
            variant={ACTION_META[action].destructive ? "destructive" : "outline"}
            disabled={pending}
            onClick={() => (needsDialog(action) ? setDialog(action) : run(action))}
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
        onOpenChange={(open) => !open && setDialog(null)}
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
  const { pending, run } = useEventTransition(eventId)
  const [dialog, setDialog] = useState<EventAction | null>(null)

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger
          render={
            <Button
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
        onOpenChange={(open) => !open && setDialog(null)}
        onConfirm={run}
      />
    </>
  )
}
