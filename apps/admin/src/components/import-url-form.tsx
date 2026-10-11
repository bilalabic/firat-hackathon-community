"use client"

import { useActionState } from "react"
import Link from "next/link"
import { CopyIcon, LoaderCircleIcon } from "lucide-react"

import { FormMessage } from "@/components/api-error-state"
import { FormField } from "@/components/form-field"
import { useFocusOnError } from "@/hooks/use-focus-on-error"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { importFromUrl, type ImportFormState } from "@/lib/actions/imports"
import { IDLE } from "@/lib/form-state"
import { URL_MAX_LENGTH } from "@/lib/imports"

export function ImportUrlForm() {
  const [state, formAction, pending] = useActionState<ImportFormState, FormData>(importFromUrl, IDLE)
  const formRef = useFocusOnError(state)
  const values = state.values ?? {}
  const errors = state.status === "error" ? (state.fieldErrors ?? {}) : {}

  return (
    <form ref={formRef} action={formAction} className="grid max-w-3xl gap-4" aria-busy={pending}>
      <Card>
        <CardContent key={JSON.stringify(values)} className="grid gap-4">
          <FormField
            id="import-url"
            label="Event page URL"
            required
            hint="The organizer's page or the event platform page (Devpost, Patika, …)."
            error={errors.url}
          >
            {(control) => (
              <Input
                {...control}
                name="url"
                type="url"
                required
                maxLength={URL_MAX_LENGTH}
                placeholder="https://"
                defaultValue={values.url}
                disabled={pending}
              />
            )}
          </FormField>
        </CardContent>
      </Card>
      {pending ? (
        <p role="status" className="flex items-center gap-2 text-sm text-muted-foreground">
          <LoaderCircleIcon className="size-4 animate-spin" aria-hidden />
          Fetching the page and extracting fields… up to a minute (longer when the local LLM is
          starting).
        </p>
      ) : state.duplicateEventId ? (
        <Alert variant="warning">
          <CopyIcon />
          <AlertTitle>Already imported</AlertTitle>
          <AlertDescription>
            {state.message}{" "}
            <Link href={`/events/${state.duplicateEventId}/review`}>Open the existing event</Link>
          </AlertDescription>
        </Alert>
      ) : (
        <FormMessage status={state.status} message={state.message} />
      )}
      <div>
        <Button type="submit" disabled={pending}>
          {pending ? "Importing…" : "Import"}
        </Button>
      </div>
    </form>
  )
}
