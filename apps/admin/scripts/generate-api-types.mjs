// Regenerates src/lib/api/schema.ts from the running API's OpenAPI document.
//
// Needs the API running and ADMIN_API_URL / ADMIN_API_TOKEN (from the environment or
// apps/admin/.env.local). The schema is served only with the bearer token, which the
// openapi-typescript CLI cannot send, so this script fetches it and uses the Node API.
// Usage: pnpm --filter admin run api:types

import { existsSync } from "node:fs";
import { writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

import openapiTS, { COMMENT_HEADER, astToString } from "openapi-typescript";

const root = fileURLToPath(new URL("..", import.meta.url));
const envFile = `${root}.env.local`;
if (existsSync(envFile)) process.loadEnvFile(envFile);

const baseUrl = (process.env.ADMIN_API_URL || "http://127.0.0.1:8000").replace(/\/+$/, "");
const token = process.env.ADMIN_API_TOKEN;
if (!token) {
  console.error("ADMIN_API_TOKEN is not set (apps/admin/.env.local).");
  process.exit(1);
}

let response;
try {
  response = await fetch(`${baseUrl}/openapi.json`, {
    headers: { Authorization: `Bearer ${token}` },
  });
} catch (error) {
  console.error(`API not reachable at ${baseUrl}: ${error.cause?.code ?? error.message}`);
  process.exit(1);
}
if (!response.ok) {
  console.error(`GET ${baseUrl}/openapi.json failed: HTTP ${response.status}`);
  process.exit(1);
}

const ast = await openapiTS(await response.json(), { exportType: true });
const output = `${root}src/lib/api/schema.ts`;
await writeFile(output, COMMENT_HEADER + astToString(ast));
console.log(`Wrote ${output}`);
