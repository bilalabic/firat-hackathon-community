import { hasBearer } from "@/lib/bearer";
import { supabase } from "@/lib/supabase";

// Daily Vercel Cron (apps/web/vercel.json, D-19). Vercel sends Authorization: Bearer <CRON_SECRET>.
// Reading the request headers makes this handler request-time only: never prerendered or cached.

export async function GET(request: Request) {
  if (!hasBearer(request, process.env.CRON_SECRET)) {
    return Response.json({ error: "unauthorized" }, { status: 401 });
  }

  const { data, error } = await supabase().rpc("keep_alive", { source: "vercel_cron" });
  if (error) {
    console.error(`[keep-alive] rpc failed: ${error.code ?? "unknown"}`);
    return Response.json({ ok: false }, { status: 502, headers: { "Cache-Control": "no-store" } });
  }
  return Response.json({ ok: true, published: data }, { headers: { "Cache-Control": "no-store" } });
}
