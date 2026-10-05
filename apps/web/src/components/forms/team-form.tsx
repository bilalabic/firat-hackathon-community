"use client";

import { submitTeamApplication } from "@/app/katki/actions";
import { Input } from "@/components/ui/input";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { Textarea } from "@/components/ui/textarea";
import { teamForm as copy } from "@/lib/copy";

import {
  ChoiceGroup,
  ConsentField,
  Field,
  FormStatus,
  FormSuccess,
  GuardFields,
  PrivacyNotice,
  SubmitButton,
  useApplicationForm,
} from "./form-kit";

export function TeamForm() {
  const { state, pending, formProps, errors, statusRef } = useApplicationForm(submitTeamApplication);

  if (state.status === "success") return <FormSuccess message={copy.success} statusRef={statusRef} />;

  return (
    <form {...formProps} className="relative space-y-6">
      <FormStatus state={state} statusRef={statusRef} />
      <GuardFields />

      <div className="grid gap-6 sm:grid-cols-2">
        <Field id="full_name" label={copy.fullName} required error={errors.full_name}>
          {(props) => <Input {...props} autoComplete="name" maxLength={120} className="h-10" />}
        </Field>
        <Field id="affiliation" label={copy.affiliation} error={errors.affiliation}>
          {(props) => <Input {...props} autoComplete="organization" maxLength={160} className="h-10" />}
        </Field>
      </div>

      <ChoiceGroup
        name="areas"
        type="checkbox"
        legend={copy.areas}
        hint={copy.areasHint}
        options={copy.areaOptions}
        required
        error={errors.areas}
      />

      <Field id="skills" label={copy.skills} hint={copy.skillsHint} error={errors.skills}>
        {(props) => <Textarea {...props} maxLength={500} rows={3} />}
      </Field>

      <div className="grid gap-6 sm:grid-cols-2">
        <Field id="github_url" label={copy.githubUrl} error={errors.github_url}>
          {(props) => (
            <Input {...props} type="url" inputMode="url" placeholder="https://github.com/…" maxLength={200} className="h-10" />
          )}
        </Field>
        <Field id="linkedin_url" label={copy.linkedinUrl} error={errors.linkedin_url}>
          {(props) => (
            <Input {...props} type="url" inputMode="url" placeholder="https://www.linkedin.com/in/…" maxLength={200} className="h-10" />
          )}
        </Field>
      </div>

      <Field id="availability" label={copy.availability} error={errors.availability}>
        {(props) => (
          <NativeSelect {...props} defaultValue="" className="w-full sm:w-72 [&_select]:h-10">
            <NativeSelectOption value="">{copy.availabilityPlaceholder}</NativeSelectOption>
            {Object.entries(copy.availabilityOptions).map(([value, label]) => (
              <NativeSelectOption key={value} value={value}>
                {label}
              </NativeSelectOption>
            ))}
          </NativeSelect>
        )}
      </Field>

      <Field id="motivation" label={copy.motivation} error={errors.motivation}>
        {(props) => <Textarea {...props} maxLength={1000} rows={4} />}
      </Field>

      <PrivacyNotice />
      <ConsentField error={errors.consent} />

      <SubmitButton pending={pending} />
    </form>
  );
}
