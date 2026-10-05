import { describe, expect, it } from "vitest";

import { hasBearer } from "./bearer";
import { parseRevalidateBody } from "./cache-tags";
import { safeExternalUrl } from "./format";
import { serializeJsonLd } from "./json-ld";
import { resolveSiteUrl } from "./site-url";

const request = (authorization?: string) =>
  new Request("http://localhost/api/x", {
    headers: authorization === undefined ? {} : { authorization },
  });

describe("hasBearer", () => {
  it("accepts the exact secret", () => {
    expect(hasBearer(request("Bearer s3cret-value"), "s3cret-value")).toBe(true);
  });
  it("rejects a wrong or missing token", () => {
    expect(hasBearer(request("Bearer wrong"), "s3cret-value")).toBe(false);
    expect(hasBearer(request(), "s3cret-value")).toBe(false);
    expect(hasBearer(request("s3cret-value"), "s3cret-value")).toBe(false);
  });
  it("never matches when the secret is unset or empty", () => {
    expect(hasBearer(request("Bearer "), "")).toBe(false);
    expect(hasBearer(request("Bearer undefined"), undefined)).toBe(false);
  });
  it("requires the scheme as written (Bearer)", () => {
    expect(hasBearer(request("bearer s3cret-value"), "s3cret-value")).toBe(false);
  });
});

describe("serializeJsonLd", () => {
  it("escapes < so content cannot close the script element", () => {
    const json = serializeJsonLd({ name: "</script><script>alert(1)</script>" });
    expect(json).not.toContain("<");
    expect(json).toContain("\\u003c/script>");
    expect(JSON.parse(json)).toEqual({ name: "</script><script>alert(1)</script>" });
  });
});

describe("safeExternalUrl", () => {
  it("keeps http(s) links", () => {
    expect(safeExternalUrl("https://example.com/a?b=1")).toBe("https://example.com/a?b=1");
    expect(safeExternalUrl("http://example.com")).toBe("http://example.com/");
  });
  it("drops other schemes and junk", () => {
    expect(safeExternalUrl("javascript:alert(1)")).toBeNull();
    expect(safeExternalUrl(" JavaScript:alert(1)")).toBeNull();
    expect(safeExternalUrl("data:text/html,<b>x</b>")).toBeNull();
    expect(safeExternalUrl("not a url")).toBeNull();
    expect(safeExternalUrl(null)).toBeNull();
  });
});

describe("parseRevalidateBody", () => {
  it("accepts the two tag shapes and removes duplicates", () => {
    expect(parseRevalidateBody({ tags: ["events", "event:grid-up", "events"] })).toEqual([
      "events",
      "event:grid-up",
    ]);
  });
  it.each([
    [{ tags: [] }],
    [{ tags: ["_N_T_/layout"] }],
    [{ tags: ["event:Bad Slug"] }],
    [{ tags: ["event:"] }],
    [{ tags: [`event:${"a".repeat(81)}`] }],
    [{ tags: "events" }],
    [{ tags: ["events"], extra: true }],
    [null],
    ["events"],
  ])("rejects %j", (body) => {
    expect(parseRevalidateBody(body)).toBeNull();
  });
});

describe("resolveSiteUrl", () => {
  it("prefers NEXT_PUBLIC_SITE_URL and strips a trailing slash", () => {
    expect(resolveSiteUrl({ NEXT_PUBLIC_SITE_URL: "https://fhc.example/" })).toBe("https://fhc.example");
  });
  it("falls back to the Vercel production domain", () => {
    expect(resolveSiteUrl({ VERCEL_ENV: "production", VERCEL_PROJECT_PRODUCTION_URL: "fhc.vercel.app" })).toBe(
      "https://fhc.vercel.app",
    );
  });
  it("fails in production without any site URL", () => {
    expect(() => resolveSiteUrl({ VERCEL_ENV: "production" })).toThrow(/NEXT_PUBLIC_SITE_URL/);
  });
  it("uses localhost for local development", () => {
    expect(resolveSiteUrl({})).toBe("http://localhost:3000");
  });
});
