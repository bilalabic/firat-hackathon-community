"use server";

import { parseTeamForm } from "@/lib/forms/schemas";
import type { FormState } from "@/lib/forms/state";
import { submitApplication } from "@/lib/forms/submit";

export async function submitTeamApplication(
  _previous: FormState,
  formData: FormData,
): Promise<FormState> {
  return submitApplication(formData, parseTeamForm, "submit_team_application");
}
