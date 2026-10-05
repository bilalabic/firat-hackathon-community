// Absolute site URL for canonical links, the sitemap, robots and JSON-LD. Server code only.

type Env = Record<string, string | undefined>;

/**
 * NEXT_PUBLIC_SITE_URL, else the Vercel production domain (VERCEL_PROJECT_PRODUCTION_URL, set
 * on Vercel even for previews), else localhost for local development. A production deployment
 * without either fails the build instead of publishing localhost canonical URLs.
 */
export function resolveSiteUrl(env: Env): string {
  const explicit = env.NEXT_PUBLIC_SITE_URL?.trim();
  if (explicit) return explicit.replace(/\/+$/, "");
  const vercelDomain = env.VERCEL_PROJECT_PRODUCTION_URL?.trim();
  if (vercelDomain) return `https://${vercelDomain.replace(/\/+$/, "")}`;
  if (env.VERCEL_ENV === "production") {
    throw new Error("NEXT_PUBLIC_SITE_URL must be set for production deployments.");
  }
  return "http://localhost:3000";
}

export function siteUrl(): string {
  return resolveSiteUrl(process.env);
}

export function absoluteUrl(path: string): string {
  return `${siteUrl()}${path}`;
}
