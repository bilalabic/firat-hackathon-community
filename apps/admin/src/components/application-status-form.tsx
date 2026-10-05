"use client"

import { useState, useTransition } from "react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select"
import { updateApplicationStatus } from "@/lib/actions/applications"
import type { ApplicationStatus } from "@/lib/api/types"
import { APPLICATION_STATUSES, APPLICATION_STATUS_LABELS } from "@/lib/applications"

/**
 * Status select + Save (an explicit button, so arrow keys on the select do not send
 * several updates). Receives the id and status only, no personal data.
 */
export function ApplicationStatusForm({
  kind,
  id,
  status,
  label,
}: {
  kind: "community" | "team"
  id: string
  status: ApplicationStatus
  /** Accessible name of the select, e.g. "Status of the application from Ada". */
  label: string
}) {
  const [value, setValue] = useState<ApplicationStatus>(status)
  const [pending, startTransition] = useTransition()

  return (
    <form
      className="flex items-center gap-2"
      onSubmit={(event) => {
        event.preventDefault()
        startTransition(async () => {
          const result = await updateApplicationStatus({ kind, id, status: value })
          if (result.ok) toast.success(`Status set to ${APPLICATION_STATUS_LABELS[value]}.`)
          else toast.error(result.message)
        })
      }}
    >
      <NativeSelect
        size="sm"
        aria-label={label}
        value={value}
        disabled={pending}
        onChange={(event) => setValue(event.target.value as ApplicationStatus)}
      >
        {APPLICATION_STATUSES.map((option) => (
          <NativeSelectOption key={option} value={option}>
            {APPLICATION_STATUS_LABELS[option]}
          </NativeSelectOption>
        ))}
      </NativeSelect>
      <Button type="submit" size="sm" variant="outline" disabled={pending || value === status}>
        Save
      </Button>
    </form>
  )
}
