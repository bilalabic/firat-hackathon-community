"use client";

import { CheckCircle2 } from "lucide-react";
import Link from "next/link";
import {
  startTransition,
  useActionState,
  useEffect,
  useRef,
  type FormEvent,
  type ReactNode,
  type RefObject,
} from "react";

import { buttonVariants } from "@/components/ui/button";
import { common, form } from "@/lib/copy";
import { ELAPSED_FIELD, HONEYPOT_FIELD } from "@/lib/forms/guard";
import { initialFormState, type FormState } from "@/lib/forms/state";
import { privacyNotice } from "@/lib/privacy";
import { routes } from "@/lib/routes";
import { cn } from "@/lib/utils";

type Action = (state: FormState, formData: FormData) => Promise<FormState>;

/**
 * Wires a form to its Server Action.
 * - The Server Action is the form's `action`, so before hydration or without JavaScript the
 *   browser POSTs to it (progressive enhancement): personal data never ends up in a GET URL.
 *   Such a submit carries no fill time and is rejected with a "JavaScript needed" message.
 * - After hydration, onSubmit takes over (preventDefault stops the native/action submit): it adds
 *   the fill time measured on the client (lib/forms/guard.ts) and dispatches without React's
 *   automatic form reset, so a validation error keeps what the user typed.
 * - Focus moves to the error summary or the success message.
 */
export function useApplicationForm(action: Action) {
  const [state, dispatch, pending] = useActionState(action, initialFormState);
  const mountedAt = useRef(0);
  const statusRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    mountedAt.current = Date.now();
  }, []);

  useEffect(() => {
    if (state.status !== "idle") statusRef.current?.focus();
  }, [state]);

  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    formData.set(ELAPSED_FIELD, String(Date.now() - mountedAt.current));
    startTransition(() => dispatch(formData));
  };

  const errors = state.status === "error" ? (state.fieldErrors ?? {}) : {};
  const formProps = { action: dispatch, onSubmit, noValidate: true } as const;
  return { state, pending, formProps, errors, statusRef };
}

/** The bot-filter fields every application form carries. */
export function GuardFields() {
  return (
    <>
      {/* Filled in by onSubmit; stays empty on a no-JavaScript submit. */}
      <input type="hidden" name={ELAPSED_FIELD} defaultValue="" />
      <Honeypot />
    </>
  );
}

export function describedBy(id: string, { hint, error }: { hint?: boolean; error?: string }) {
  const ids = [hint ? `${id}-hint` : null, error ? `${id}-error` : null].filter(Boolean);
  return ids.length ? ids.join(" ") : undefined;
}

function FieldMeta({ id, hint, error }: { id: string; hint?: string; error?: string }) {
  return (
    <>
      {hint ? (
        <p id={`${id}-hint`} className="text-sm text-muted-foreground">
          {hint}
        </p>
      ) : null}
      {error ? (
        <p id={`${id}-error`} className="text-sm font-medium text-destructive">
          {error}
        </p>
      ) : null}
    </>
  );
}

function LabelText({ label, required }: { label: string; required?: boolean }) {
  return (
    <>
      {label}
      <span className="font-normal text-muted-foreground">
        {" "}
        ({required ? form.required : form.optional})
      </span>
    </>
  );
}

/** Label + control + hint + error. The control gets its id and aria props from `children`. */
export function Field({
  id,
  label,
  required,
  hint,
  error,
  children,
}: {
  id: string;
  label: string;
  required?: boolean;
  hint?: string;
  error?: string;
  children: (props: {
    id: string;
    name: string;
    "aria-invalid": boolean | undefined;
    "aria-describedby": string | undefined;
    "aria-required": boolean | undefined;
  }) => ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={id} className="block text-sm font-medium">
        <LabelText label={label} required={required} />
      </label>
      {children({
        id,
        name: id,
        "aria-invalid": error ? true : undefined,
        "aria-describedby": describedBy(id, { hint: !!hint, error }),
        "aria-required": required || undefined,
      })}
      <FieldMeta id={id} hint={hint} error={error} />
    </div>
  );
}

/** A group of native checkboxes or radios in a fieldset. */
export function ChoiceGroup({
  name,
  type,
  legend,
  options,
  required,
  hint,
  error,
  value,
  onValueChange,
  columns = 2,
}: {
  name: string;
  type: "checkbox" | "radio";
  legend: string;
  options: Record<string, string>;
  required?: boolean;
  hint?: string;
  error?: string;
  value?: string;
  onValueChange?: (value: string) => void;
  columns?: 1 | 2;
}) {
  return (
    <fieldset
      className="space-y-2"
      aria-describedby={describedBy(name, { hint: !!hint, error })}
    >
      <legend className="text-sm font-medium">
        <LabelText label={legend} required={required} />
      </legend>
      <FieldMeta id={name} hint={hint} error={error} />
      <div className={cn("grid gap-x-6 gap-y-1", columns === 2 && "sm:grid-cols-2")}>
        {Object.entries(options).map(([optionValue, label]) => (
          <label
            key={optionValue}
            className="flex min-h-10 cursor-pointer items-center gap-3 rounded-md text-[15px]"
          >
            <input
              type={type}
              name={name}
              value={optionValue}
              checked={value === undefined ? undefined : value === optionValue}
              onChange={onValueChange ? (event) => onValueChange(event.target.value) : undefined}
              className="size-4 shrink-0 accent-brand"
            />
            {label}
          </label>
        ))}
      </div>
    </fieldset>
  );
}

/** Hidden from people (and assistive tech); naive bots fill it in. */
export function Honeypot() {
  return (
    <div aria-hidden="true" className="absolute -left-[9999px] h-px w-px overflow-hidden">
      <label>
        {form.honeypotLabel}
        <input type="text" name={HONEYPOT_FIELD} tabIndex={-1} autoComplete="off" defaultValue="" />
      </label>
    </div>
  );
}

/** Short KVKK summary next to the consent box; the full notice lives at /aydinlatma-metni. */
export function PrivacyNotice() {
  return (
    <section aria-labelledby="aydinlatma-metni" className="space-y-2 rounded-lg border p-4 text-sm">
      <h3 id="aydinlatma-metni" className="font-medium">
        {form.privacyTitle}
      </h3>
      <p className="text-muted-foreground">{privacyNotice.formSummary}</p>
      <p>
        <Link href={routes.privacy} target="_blank" rel="noopener" className="font-medium text-brand underline underline-offset-4">
          {privacyNotice.formLinkLabel}
        </Link>
        <span className="text-muted-foreground"> {common.opensInNewTab}</span>
      </p>
    </section>
  );
}

export function ConsentField({ error }: { error?: string }) {
  return (
    <div className="space-y-1.5">
      <label className="flex cursor-pointer items-start gap-3 text-[15px]">
        <input
          type="checkbox"
          name="consent"
          aria-required="true"
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? "consent-error" : undefined}
          className="mt-1 size-4 shrink-0 accent-brand"
        />
        <span>
          {form.consentLabel}
          <span className="text-muted-foreground"> ({form.required})</span>
        </span>
      </label>
      <FieldMeta id="consent" error={error} />
    </div>
  );
}

export function FormStatus({
  state,
  statusRef,
}: {
  state: FormState;
  statusRef: RefObject<HTMLDivElement | null>;
}) {
  if (state.status !== "error") return null;
  return (
    <div
      ref={statusRef}
      tabIndex={-1}
      role="alert"
      className="rounded-lg border border-destructive/40 bg-destructive/5 px-4 py-3 text-sm font-medium text-destructive"
    >
      {state.message}
    </div>
  );
}

export function FormSuccess({
  message,
  statusRef,
}: {
  message: string;
  statusRef: RefObject<HTMLDivElement | null>;
}) {
  return (
    <div
      ref={statusRef}
      tabIndex={-1}
      role="status"
      className="space-y-2 rounded-lg border border-open/30 bg-open-soft p-6"
    >
      <p className="flex items-center gap-2 text-lg font-semibold text-open">
        <CheckCircle2 aria-hidden="true" className="size-5" />
        {form.successTitle}
      </p>
      <p>{message}</p>
    </div>
  );
}

export function SubmitButton({ pending }: { pending: boolean }) {
  return (
    <div>
      <button type="submit" disabled={pending} className={cn(buttonVariants(), "h-11 px-5")}>
        {pending ? form.submitting : form.submit}
      </button>
      <span role="status" className="sr-only">
        {pending ? form.submitting : ""}
      </span>
    </div>
  );
}
