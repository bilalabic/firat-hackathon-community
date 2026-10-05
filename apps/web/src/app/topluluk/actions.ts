"use server";

import { parseCommunityForm } from "@/lib/forms/schemas";
import type { FormState } from "@/lib/forms/state";
import { submitApplication } from "@/lib/forms/submit";

export async function submitCommunityApplication(
  _previous: FormState,
  formData: FormData,
): Promise<FormState> {
  return submitApplication(formData, parseCommunityForm, "submit_community_application");
}
