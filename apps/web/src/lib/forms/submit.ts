import "server-only";

import { form } from "../copy";
import type { Json } from "../database.types";
import { supabase } from "../supabase";
import { checkBotGuards } from "./guard";
import type { ParseResult } from "./schemas";
import type { FormState } from "./state";

type SubmitFunction = "submit_community_application" | "submit_team_application";

/**
 * Shared pipeline of the form Server Actions (PUBLIC_WEB §3):
 * honeypot + timing → zod validation → api.submit_* RPC → generic result.
 */
export async function submitApplication<T extends Record<string, Json | undefined>>(
  formData: FormData,
  parse: (formData: FormData) => ParseResult<T>,
  fn: SubmitFunction,
): Promise<FormState> {
  const guard = checkBotGuards(formData);
  // A filled honeypot is answered like a success so bots learn nothing; nothing is stored.
  if (guard === "honeypot") return { status: "success" };
  if (guard === "too_fast") return { status: "error", message: form.tooFast };

  const parsed = parse(formData);
  if (!parsed.success) {
    return { status: "error", message: form.errorSummary, fieldErrors: parsed.fieldErrors };
  }

  const { error } = await supabase().rpc(fn, { payload: parsed.payload });
  if (error) {
    // Log the code only: the payload is personal data and must not reach the logs.
    console.error(`[forms] ${fn} failed: ${error.code ?? "unknown"}`);
    return { status: "error", message: form.genericError };
  }
  return { status: "success" };
}
