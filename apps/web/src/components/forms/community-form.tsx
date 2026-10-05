"use client";

import { useState } from "react";

import { submitCommunityApplication } from "@/app/topluluk/actions";
import { Input } from "@/components/ui/input";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { Textarea } from "@/components/ui/textarea";
import { communityForm as copy } from "@/lib/copy";

import {
  ChoiceGroup,
  ConsentField,
  Field,
  FormStatus,
  FormSuccess,
  Honeypot,
  PrivacyNotice,
  SubmitButton,
  useApplicationForm,
} from "./form-kit";

export function CommunityForm() {
  const { state, pending, onSubmit, errors, statusRef } = useApplicationForm(submitCommunityApplication);
  const [channel, setChannel] = useState<string>("");

  if (state.status === "success") return <FormSuccess message={copy.success} statusRef={statusRef} />;

  return (
    <form onSubmit={onSubmit} noValidate className="relative space-y-6">
      <FormStatus state={state} statusRef={statusRef} />
      <Honeypot />

      <Field id="full_name" label={copy.fullName} required error={errors.full_name}>
        {(props) => <Input {...props} autoComplete="name" maxLength={120} className="h-10" />}
      </Field>

      <div className="grid gap-6 sm:grid-cols-2">
        <Field id="university" label={copy.university} error={errors.university}>
          {(props) => <Input {...props} autoComplete="organization" maxLength={160} className="h-10" />}
        </Field>
        <Field id="field_of_study" label={copy.fieldOfStudy} error={errors.field_of_study}>
          {(props) => <Input {...props} maxLength={120} className="h-10" />}
        </Field>
        <Field id="year_of_study" label={copy.yearOfStudy} error={errors.year_of_study}>
          {(props) => (
            <NativeSelect {...props} defaultValue="" className="w-full [&_select]:h-10">
              <NativeSelectOption value="">{copy.yearPlaceholder}</NativeSelectOption>
              {Object.entries(copy.years).map(([value, label]) => (
                <NativeSelectOption key={value} value={value}>
                  {label}
                </NativeSelectOption>
              ))}
            </NativeSelect>
          )}
        </Field>
        <Field id="experience_level" label={copy.experienceLevel} error={errors.experience_level}>
          {(props) => (
            <NativeSelect {...props} defaultValue="" className="w-full [&_select]:h-10">
              <NativeSelectOption value="">{copy.experiencePlaceholder}</NativeSelectOption>
              {Object.entries(copy.experienceLevels).map(([value, label]) => (
                <NativeSelectOption key={value} value={value}>
                  {label}
                </NativeSelectOption>
              ))}
            </NativeSelect>
          )}
        </Field>
      </div>

      <ChoiceGroup
        name="interests"
        type="checkbox"
        legend={copy.interests}
        hint={copy.interestsHint}
        options={copy.interestOptions}
        error={errors.interests}
      />

      <Field id="looking_for" label={copy.lookingFor} hint={copy.lookingForHint} error={errors.looking_for}>
        {(props) => <Textarea {...props} maxLength={500} rows={3} />}
      </Field>

      <div className="space-y-4 rounded-lg border p-4 sm:p-5">
        <ChoiceGroup
          name="preferred_channel"
          type="radio"
          legend={copy.channel}
          hint={copy.channelHint}
          options={copy.channels}
          required
          value={channel}
          onValueChange={setChannel}
          error={errors.preferred_channel}
        />
        {/* Contact data only for the chosen channel (SECURITY §7). */}
        {channel === "telegram" ? (
          <Field
            id="telegram_username"
            label={copy.telegramUsername}
            hint={copy.telegramHint}
            required
            error={errors.telegram_username}
          >
            {(props) => (
              <Input {...props} autoComplete="off" autoCapitalize="none" spellCheck={false} maxLength={33} className="h-10" />
            )}
          </Field>
        ) : null}
        {channel === "whatsapp" ? (
          <Field id="phone" label={copy.phone} hint={copy.phoneHint} required error={errors.phone}>
            {(props) => <Input {...props} type="tel" inputMode="tel" autoComplete="tel" maxLength={20} className="h-10" />}
          </Field>
        ) : null}
      </div>

      <Field id="message" label={copy.message} error={errors.message}>
        {(props) => <Textarea {...props} maxLength={1000} rows={4} />}
      </Field>

      <PrivacyNotice />
      <ConsentField error={errors.consent} />

      <SubmitButton pending={pending} />
    </form>
  );
}
