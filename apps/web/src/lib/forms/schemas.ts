// Form validation mirroring the DB rules in supabase/migrations/20260928120000_core_schema.sql
// (app.community_applications, app.team_applications) and the api.submit_* functions.
// Pure: used by the Server Actions and by unit tests.

import { z } from "zod";

import { communityForm, form, teamForm } from "../copy";

// v2: the approved KVKK notice (lib/privacy.ts) incl. explicit consent to the transfer abroad.
export const COMMUNITY_CONSENT_VERSION = "2026-10-community-v2";
export const TEAM_CONSENT_VERSION = "2026-10-team-v2";

export type FieldErrors = Record<string, string>;
export type ParseResult<T> =
  | { success: true; payload: T }
  | { success: false; fieldErrors: FieldErrors };

const keysOf = <T extends Record<string, string>>(record: T) =>
  Object.keys(record) as [keyof T & string, ...(keyof T & string)[]];

export const yearOfStudyValues = keysOf(communityForm.years);
export const experienceLevelValues = keysOf(communityForm.experienceLevels);
export const interestValues = keysOf(communityForm.interestOptions);
export const channelValues = keysOf(communityForm.channels);
export const areaValues = keysOf(teamForm.areaOptions);
export const availabilityValues = keysOf(teamForm.availabilityOptions);

/**
 * Normalizes a phone number to E.164. Turkish mobile numbers may be written as
 * "0532 123 45 67", "532 123 45 67", "90532…" or "+90 532…". Other countries need "+" or "00".
 * Returns null when the result would not satisfy the DB rule ^\+[1-9][0-9]{7,14}$.
 */
export function normalizePhone(raw: string): string | null {
  const compact = raw.replace(/[\s().-]/g, "");
  let e164: string;
  if (/^0?5\d{9}$/.test(compact)) e164 = `+90${compact.slice(-10)}`;
  else if (/^905\d{9}$/.test(compact)) e164 = `+${compact}`;
  else if (compact.startsWith("00")) e164 = `+${compact.slice(2)}`;
  else e164 = compact;
  if (!/^\+[1-9]\d{7,14}$/.test(e164)) return null;
  // A Turkish number must be a mobile number (WhatsApp).
  if (e164.startsWith("+90") && !/^\+905\d{9}$/.test(e164)) return null;
  return e164;
}

/** Strips a leading "@". Null unless it satisfies ^[A-Za-z0-9_]{5,32}$. */
export function normalizeTelegramUsername(raw: string): string | null {
  const username = raw.trim().replace(/^@/, "");
  return /^[A-Za-z0-9_]{5,32}$/.test(username) ? username : null;
}

// --- building blocks -----------------------------------------------------------------------

const text = (max: number) =>
  z
    .string()
    .trim()
    .max(max, form.errors.tooLong(max))
    .transform((value) => value || undefined);

const fullName = z.string().trim().min(2, form.errors.fullName).max(120, form.errors.fullName);

const choice = <T extends [string, ...string[]]>(values: T) =>
  z
    .union([z.literal(""), z.enum(values, { error: form.errors.choose })])
    .transform((value) => (value === "" ? undefined : (value as T[number])));

const consent = z.literal("on", { error: form.errors.consent });

/** The checkbox is required but not stored; consent_version records what was agreed to. */
function withoutConsent<T extends { consent: unknown }>(data: T): Omit<T, "consent"> {
  const rest: Partial<T> = { ...data };
  delete rest.consent;
  return rest as Omit<T, "consent">;
}

const httpsProfile = (pattern: RegExp, message: string) =>
  text(200).refine((value) => value === undefined || pattern.test(value), message);

// --- form data ------------------------------------------------------------------------------

function read(formData: FormData, name: string): string {
  const value = formData.get(name);
  return typeof value === "string" ? value : "";
}

function readAll(formData: FormData, name: string): string[] {
  return formData.getAll(name).filter((value): value is string => typeof value === "string");
}

function toFieldErrors(error: z.ZodError): FieldErrors {
  const errors: FieldErrors = {};
  for (const issue of error.issues) {
    const key = String(issue.path[0] ?? "form");
    errors[key] ??= issue.message;
  }
  return errors;
}

// --- community ------------------------------------------------------------------------------

const communitySchema = z
  .object({
    full_name: fullName,
    university: text(160),
    field_of_study: text(120),
    year_of_study: choice(yearOfStudyValues),
    interests: z
      .array(z.enum(interestValues, { error: form.errors.choose }))
      .max(10, form.errors.interests),
    experience_level: choice(experienceLevelValues),
    looking_for: text(500),
    preferred_channel: z.enum(channelValues, { error: form.errors.channel }),
    message: text(1000),
    consent,
  })
  .transform((data) => ({
    ...withoutConsent(data),
    interests: [...new Set(data.interests)],
    consent_version: COMMUNITY_CONSENT_VERSION,
  }));

type ChannelContact = { telegram_username: string } | { phone: string };

export type CommunityPayload = z.output<typeof communitySchema> & ChannelContact;

// The contact field depends on the chosen channel; it is validated outside the object schema
// so its error is reported together with the other field errors.
function parseContact(formData: FormData): { contact?: ChannelContact; errors: FieldErrors } {
  const channel = read(formData, "preferred_channel");
  if (channel === "telegram") {
    const username = normalizeTelegramUsername(read(formData, "telegram_username"));
    return username
      ? { contact: { telegram_username: username }, errors: {} }
      : { errors: { telegram_username: form.errors.telegram } };
  }
  if (channel === "whatsapp") {
    const phone = normalizePhone(read(formData, "phone"));
    return phone ? { contact: { phone }, errors: {} } : { errors: { phone: form.errors.phone } };
  }
  return { errors: {} }; // preferred_channel itself is reported by the schema
}

export function parseCommunityForm(formData: FormData): ParseResult<CommunityPayload> {
  const result = communitySchema.safeParse({
    full_name: read(formData, "full_name"),
    university: read(formData, "university"),
    field_of_study: read(formData, "field_of_study"),
    year_of_study: read(formData, "year_of_study"),
    interests: readAll(formData, "interests"),
    experience_level: read(formData, "experience_level"),
    looking_for: read(formData, "looking_for"),
    preferred_channel: read(formData, "preferred_channel"),
    message: read(formData, "message"),
    consent: read(formData, "consent"),
  });
  const { contact, errors } = parseContact(formData);
  if (!result.success || !contact) {
    return {
      success: false,
      fieldErrors: { ...(result.success ? {} : toFieldErrors(result.error)), ...errors },
    };
  }
  // Contact data only for the chosen channel (data minimisation, SECURITY §7).
  return { success: true, payload: { ...result.data, ...contact } };
}

// --- team -----------------------------------------------------------------------------------

const teamSchema = z
  .object({
    full_name: fullName,
    affiliation: text(160),
    areas: z
      .array(z.enum(areaValues, { error: form.errors.choose }))
      .min(1, form.errors.areas)
      .max(areaValues.length),
    skills: text(500),
    github_url: httpsProfile(/^https:\/\/(www\.)?github\.com\//, form.errors.github),
    linkedin_url: httpsProfile(
      /^https:\/\/([a-z]{2,3}\.)?(www\.)?linkedin\.com\//,
      form.errors.linkedin,
    ),
    availability: choice(availabilityValues),
    motivation: text(1000),
    consent,
  })
  .transform((data) => ({
    ...withoutConsent(data),
    areas: [...new Set(data.areas)],
    consent_version: TEAM_CONSENT_VERSION,
  }));

export type TeamPayload = z.output<typeof teamSchema>;

export function parseTeamForm(formData: FormData): ParseResult<TeamPayload> {
  const result = teamSchema.safeParse({
    full_name: read(formData, "full_name"),
    affiliation: read(formData, "affiliation"),
    areas: readAll(formData, "areas"),
    skills: read(formData, "skills"),
    github_url: read(formData, "github_url"),
    linkedin_url: read(formData, "linkedin_url"),
    availability: read(formData, "availability"),
    motivation: read(formData, "motivation"),
    consent: read(formData, "consent"),
  });
  return result.success
    ? { success: true, payload: result.data }
    : { success: false, fieldErrors: toFieldErrors(result.error) };
}
