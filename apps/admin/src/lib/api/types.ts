// Readable aliases for the generated OpenAPI types (schema.ts). Type-only: safe to
// import from Client Components.

import type { components } from "./schema"

type Schemas = components["schemas"]

export type Overview = Schemas["OverviewOut"]
export type Heartbeat = Schemas["HeartbeatOut"]

export type Event = Schemas["EventOut"]
export type EventPage = Schemas["EventPage"]
export type EventCreate = Schemas["EventCreate"]
export type EventUpdate = Schemas["EventUpdate"]
export type EventStatus = Event["status"]
export type EventAction = Event["allowed_actions"][number]
export type VerificationStatus = Event["verification_status"]
export type EventFormat = NonNullable<Event["format"]>

export type Review = Schemas["ReviewOut"]
export type Signal = Schemas["Signal"]
export type EventSource = Schemas["EventSourceOut"]
export type EventSourceRole = EventSource["role"]

export type Source = Schemas["SourceOut"]
export type SourceCreate = Schemas["SourceCreate"]
export type SourceUpdate = Schemas["SourceUpdate"]
export type SourceKind = Source["kind"]
export type RetrievalMethod = Source["retrieval_method"]

export type CommunityApplication = Schemas["CommunityApplicationOut"]
export type TeamApplication = Schemas["TeamApplicationOut"]
export type ApplicationStatus = CommunityApplication["status"]

export type DbCheck = Schemas["DbCheckOut"]
export type LlmCheck = Schemas["LLMCheckResponse"]
export type TelegramCheck = Schemas["TelegramCheckResult"]
export type AdminBotStatus = Schemas["AdminBotStatus"]
