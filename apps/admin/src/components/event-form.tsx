"use client"

import { useActionState } from "react"

import { FormMessage } from "@/components/api-error-state"
import { FormField, type ControlProps } from "@/components/form-field"
import { useFocusOnError } from "@/hooks/use-focus-on-error"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select"
import { Textarea } from "@/components/ui/textarea"
import { EVENT_FIELD_GROUPS, type EventField, type FormValues } from "@/lib/event-form"
import { IDLE, type FormState } from "@/lib/form-state"

function Control({ field, value, control }: { field: EventField; value: string; control: ControlProps }) {
  const common = { ...control, name: field.name, defaultValue: value, required: field.required }
  switch (field.kind) {
    case "textarea":
      return <Textarea {...common} maxLength={field.maxLength} rows={field.name === "summary" ? 3 : 5} />
    case "select":
    case "boolean":
      return (
        <NativeSelect {...common} className="w-full">
          {field.options?.map((option) => (
            <NativeSelectOption key={option.value} value={option.value}>
              {option.label}
            </NativeSelectOption>
          ))}
        </NativeSelect>
      )
    case "date":
      return <Input {...common} type="date" />
    case "integer":
      return <Input {...common} type="number" inputMode="numeric" min={1} max={20} step={1} />
    case "decimal":
      return <Input {...common} inputMode="decimal" />
    case "url":
      return <Input {...common} type="url" maxLength={field.maxLength} placeholder="https://" />
    default:
      return <Input {...common} maxLength={field.maxLength} placeholder={field.placeholder} />
  }
}

export function EventForm({
  action,
  initialValues,
  submitLabel,
}: {
  action: (state: FormState, formData: FormData) => Promise<FormState>
  initialValues: FormValues
  submitLabel: string
}) {
  const [state, formAction, pending] = useActionState(action, IDLE)
  const formRef = useFocusOnError(state)
  const values = state.status === "error" && state.values ? state.values : initialValues
  const errors = state.status === "error" ? (state.fieldErrors ?? {}) : {}

  return (
    <form ref={formRef} action={formAction}className="grid gap-4" aria-busy={pending}>
      {/* Remount the fields when the values change so selects pick up new defaults. */}
      <div key={JSON.stringify(values)} className="grid gap-4 @4xl/main:grid-cols-2">
        {EVENT_FIELD_GROUPS.map((group) => (
          <Card key={group.title}>
            <CardHeader>
              <CardTitle>{group.title}</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-4 @xl/main:grid-cols-2">
              {group.fields.map((field) => (
                <FormField
                  key={field.name}
                  id={`event-${field.name}`}
                  label={
                    <>
                      {field.label}
                      {field.requiredForReview && (
                        <span className="font-normal text-muted-foreground">(needed for review)</span>
                      )}
                    </>
                  }
                  required={field.required}
                  hint={field.hint}
                  error={errors[field.name]}
                  className={field.kind === "textarea" ? "@xl/main:col-span-2" : undefined}
                >
                  {(control) => <Control field={field} value={values[field.name] ?? ""} control={control} />}
                </FormField>
              ))}
            </CardContent>
          </Card>
        ))}
      </div>
      <div className="grid gap-3">
        <FormMessage status={state.status} message={state.message} />
        <div>
          <Button type="submit" disabled={pending}>
            {pending ? "Saving…" : submitLabel}
          </Button>
        </div>
      </div>
    </form>
  )
}
