"use client"

import { useActionState } from "react"

import { FormMessage } from "@/components/api-error-state"
import { FormField } from "@/components/form-field"
import { useFocusOnError } from "@/hooks/use-focus-on-error"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select"
import { Textarea } from "@/components/ui/textarea"
import { IDLE, type FormState } from "@/lib/form-state"
import {
  RETRIEVAL_METHODS,
  SOURCE_KINDS,
  TIERS,
  humanize,
  type SourceFormValues,
} from "@/lib/sources"

function fromEcho(values: Record<string, string>): SourceFormValues {
  return {
    name: values.name ?? "",
    kind: values.kind ?? "",
    tier: values.tier ?? "",
    base_url: values.base_url ?? "",
    retrieval_method: values.retrieval_method ?? "",
    notes: values.notes ?? "",
    enabled: values.enabled === "on",
    requires_js: values.requires_js === "on",
  }
}

export function SourceForm({
  action,
  initialValues,
  submitLabel,
}: {
  action: (state: FormState, formData: FormData) => Promise<FormState>
  initialValues: SourceFormValues
  submitLabel: string
}) {
  const [state, formAction, pending] = useActionState(action, IDLE)
  const formRef = useFocusOnError(state)
  const values = state.status === "error" && state.values ? fromEcho(state.values) : initialValues
  const errors = state.status === "error" ? (state.fieldErrors ?? {}) : {}

  return (
    <form ref={formRef} action={formAction}className="grid max-w-3xl gap-4" aria-busy={pending}>
      <Card>
        <CardContent key={JSON.stringify(values)} className="grid gap-4 sm:grid-cols-2">
          <FormField id="source-name" label="Name" required error={errors.name}>
            {(control) => (
              <Input {...control} name="name" required minLength={2} maxLength={120} defaultValue={values.name} />
            )}
          </FormField>
          <FormField id="source-base-url" label="Base URL" error={errors.base_url}>
            {(control) => (
              <Input {...control} name="base_url" type="url" maxLength={500} placeholder="https://" defaultValue={values.base_url} />
            )}
          </FormField>
          <FormField id="source-kind" label="Kind" error={errors.kind}>
            {(control) => (
              <NativeSelect {...control} name="kind" defaultValue={values.kind} className="w-full">
                {SOURCE_KINDS.map((kind) => (
                  <NativeSelectOption key={kind} value={kind}>
                    {humanize(kind)}
                  </NativeSelectOption>
                ))}
              </NativeSelect>
            )}
          </FormField>
          <FormField
            id="source-tier"
            label="Tier"
            hint="1 = official organizer, 4 = weakest signal"
            error={errors.tier}
          >
            {(control) => (
              <NativeSelect {...control} name="tier" defaultValue={values.tier} className="w-full">
                {TIERS.map((tier) => (
                  <NativeSelectOption key={tier} value={String(tier)}>
                    Tier {tier}
                  </NativeSelectOption>
                ))}
              </NativeSelect>
            )}
          </FormField>
          <FormField id="source-method" label="Retrieval method" error={errors.retrieval_method}>
            {(control) => (
              <NativeSelect {...control} name="retrieval_method" defaultValue={values.retrieval_method} className="w-full">
                {RETRIEVAL_METHODS.map((method) => (
                  <NativeSelectOption key={method} value={method}>
                    {humanize(method)}
                  </NativeSelectOption>
                ))}
              </NativeSelect>
            )}
          </FormField>
          <fieldset className="grid content-start gap-3">
            <legend className="mb-2 text-sm font-medium">Options</legend>
            <div className="flex items-center gap-2">
              <Checkbox id="source-enabled" name="enabled" defaultChecked={values.enabled} />
              <Label htmlFor="source-enabled">Enabled</Label>
            </div>
            <div className="flex items-center gap-2">
              <Checkbox id="source-requires-js" name="requires_js" defaultChecked={values.requires_js} />
              <Label htmlFor="source-requires-js">Requires JavaScript</Label>
            </div>
          </fieldset>
          <FormField id="source-notes" label="Notes" error={errors.notes} className="sm:col-span-2">
            {(control) => <Textarea {...control} name="notes" maxLength={2000} rows={3} defaultValue={values.notes} />}
          </FormField>
        </CardContent>
      </Card>
      <FormMessage status={state.status} message={state.message} />
      <div>
        <Button type="submit" disabled={pending}>
          {pending ? "Saving…" : submitLabel}
        </Button>
      </div>
    </form>
  )
}
