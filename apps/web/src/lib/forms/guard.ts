// Cheap bot filters for the public forms (PUBLIC_WEB §3). Pure.
//
// Timing: the browser measures how long the form was open (elapsed_ms, from mount to submit,
// both on the client clock, so server/client clock skew does not matter) and sends it with
// the form. The value is not signed. Signing it would need another server secret, and it would
// still not stop a determined bot: the publishable key allows calling the RPC directly anyway
// (accepted risk R-07). The goal is only to drop naive form-filling bots; Turnstile is the
// planned upgrade if spam appears.

export const HONEYPOT_FIELD = "website";
export const ELAPSED_FIELD = "elapsed_ms";
export const MIN_FILL_MS = 3000;

export type GuardResult = "ok" | "honeypot" | "too_fast";

export function checkBotGuards(formData: FormData): GuardResult {
  const honeypot = formData.get(HONEYPOT_FIELD);
  if (typeof honeypot === "string" && honeypot.trim() !== "") return "honeypot";
  const elapsed = Number(formData.get(ELAPSED_FIELD));
  if (!Number.isFinite(elapsed) || elapsed < MIN_FILL_MS) return "too_fast";
  return "ok";
}
