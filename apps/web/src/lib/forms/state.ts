/** Result of a form Server Action. Never contains submitted or stored data. */
export type FormState =
  | { status: "idle" }
  | { status: "success" }
  | { status: "error"; message: string; fieldErrors?: Record<string, string> };

export const initialFormState: FormState = { status: "idle" };
