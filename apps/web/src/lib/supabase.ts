import "server-only";

import { createClient, type SupabaseClient } from "@supabase/supabase-js";

import type { Database } from "./database.types";

// Server-only (PUBLIC_WEB §2): the browser never receives a Supabase client or key.
// The publishable key can only read api.events_public and call the api.* RPCs.

export type ApiClient = SupabaseClient<Database, "api">;

let client: ApiClient | undefined;

export function supabase(): ApiClient {
  if (client) return client;
  const url = process.env.SUPABASE_URL;
  const key = process.env.SUPABASE_PUBLISHABLE_KEY;
  if (!url || !key) {
    throw new Error("SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY must be set (see apps/web/.env.example).");
  }
  client = createClient<Database, "api">(url, key, {
    db: { schema: "api" },
    auth: { persistSession: false, autoRefreshToken: false, detectSessionInUrl: false },
  });
  return client;
}
