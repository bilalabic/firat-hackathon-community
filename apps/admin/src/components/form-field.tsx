// Label + control + hint + error, wired with aria-describedby / aria-invalid.

import { cn } from "cn"

import { Label } from "@/components/ui/label"

export type ControlProps = {
  id: string
  "aria-invalid"?: true
  "aria-describedby"?: string
}

export function FormField({
  id,
  label,
  hint,
  error,
  required,
  className,
  children,
}: {
  id: string
  label: React.ReactNode
  hint?: string
  error?: string
  required?: boolean
  className?: string
  children: (control: ControlProps) => React.ReactNode
}) {
  const hintId = hint ? `${id}-hint` : undefined
  const errorId = error ? `${id}-error` : undefined
  const describedBy = [hintId, errorId].filter(Boolean).join(" ") || undefined
  return (
    <div className={cn("grid content-start gap-2", className)}>
      <Label htmlFor={id}>
        {label}
        {required && (
          <span aria-hidden className="text-destructive">
            *
          </span>
        )}
      </Label>
      {children({ id, "aria-invalid": error ? true : undefined, "aria-describedby": describedBy })}
      {hint && (
        <p id={hintId} className="text-xs text-muted-foreground">
          {hint}
        </p>
      )}
      {error && (
        <p id={errorId} className="text-xs text-destructive">
          {error}
        </p>
      )}
    </div>
  )
}
