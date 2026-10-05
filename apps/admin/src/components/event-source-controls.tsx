"use client"

import { useActionState, useState, useTransition } from "react"
import { Trash2Icon } from "lucide-react"
import { toast } from "sonner"

import { FormMessage } from "@/components/api-error-state"
import { FormField } from "@/components/form-field"
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
import { Input } from "@/components/ui/input"
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select"
import { addEventSource, removeEventSource } from "@/lib/actions/events"
import { IDLE } from "@/lib/form-state"
import { EVENT_SOURCE_ROLES, humanize } from "@/lib/sources"

export type SourceOption = { id: string; label: string }

export function AddEventSourceForm({ eventId, sources }: { eventId: string; sources: SourceOption[] }) {
  const [state, formAction, pending] = useActionState(addEventSource.bind(null, eventId), IDLE)
  const values = state.status === "error" ? (state.values ?? {}) : {}
  const errors = state.status === "error" ? (state.fieldErrors ?? {}) : {}

  return (
    <form action={formAction} className="grid gap-3" aria-busy={pending}>
      <div key={JSON.stringify(values)} className="grid gap-3 @xl/main:grid-cols-[2fr_1fr_1fr]">
        <FormField id="event-source-url" label="URL" required error={errors.url}>
          {(control) => (
            <Input {...control} name="url" type="url" required maxLength={500} placeholder="https://" defaultValue={values.url} />
          )}
        </FormField>
        <FormField id="event-source-role" label="Role" error={errors.role}>
          {(control) => (
            <NativeSelect {...control} name="role" defaultValue={values.role ?? "official"} className="w-full">
              {EVENT_SOURCE_ROLES.map((role) => (
                <NativeSelectOption key={role} value={role}>
                  {humanize(role)}
                </NativeSelectOption>
              ))}
            </NativeSelect>
          )}
        </FormField>
        <FormField id="event-source-source" label="Source" error={errors.source_id}>
          {(control) => (
            <NativeSelect {...control} name="source_id" defaultValue={values.source_id ?? ""} className="w-full">
              <NativeSelectOption value="">None</NativeSelectOption>
              {sources.map((source) => (
                <NativeSelectOption key={source.id} value={source.id}>
                  {source.label}
                </NativeSelectOption>
              ))}
            </NativeSelect>
          )}
        </FormField>
      </div>
      <FormMessage status={state.status} message={state.message} />
      <div>
        <Button type="submit" size="sm" variant="outline" disabled={pending}>
          {pending ? "Adding…" : "Add source"}
        </Button>
      </div>
    </form>
  )
}

export function RemoveEventSourceButton({
  eventId,
  eventSourceId,
  url,
}: {
  eventId: string
  eventSourceId: string
  url: string
}) {
  const [open, setOpen] = useState(false)
  const [pending, startTransition] = useTransition()

  const remove = () =>
    startTransition(async () => {
      const result = await removeEventSource({ eventId, eventSourceId })
      if (result.ok) toast.success(result.message)
      else toast.error(result.message)
      setOpen(false)
    })

  return (
    <>
      <Button variant="ghost" size="icon-sm" disabled={pending} onClick={() => setOpen(true)}>
        <Trash2Icon />
        <span className="sr-only">Remove {url}</span>
      </Button>
      <AlertDialog open={open} onOpenChange={setOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Remove this source?</AlertDialogTitle>
            <AlertDialogDescription className="break-all">{url}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <Button variant="destructive" disabled={pending} onClick={remove}>
              Remove
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}
